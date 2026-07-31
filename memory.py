"""
外部记忆系统 — ChromaDB 向量数据库

持久存储交互历史，支持语义检索。
每次对话前检索相似记忆，注入 prompt 上下文。

设计特性：
- 价值分层：只存高价值信息（偏好/个人信息/任务），过滤临时问答
- 相似度阈值：低于阈值的记忆不注入
- 时间戳：每段记忆记录时间，支持过期感知
- 冲突处理：prompt 标注"以本次对话为准"
- 隐私保护：手机号/密码/银行卡等敏感信息自动跳过
"""

from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

MEMORY_DIR = os.getenv("MEMORY_DIR", ".agent_memory")
MEMORY_COLLECTION = os.getenv("MEMORY_COLLECTION", "agent_memory")
MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "3"))
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
# 嵌入模型：本地已有缓存时完全离线加载，绝不做无谓的联网版本检查
EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
EMBED_DEVICE = os.getenv("EMBED_DEVICE", "cpu")
# 相似度阈值：低于此值的记忆不注入（余弦距离转相似度后比较）
MEMORY_MIN_SIMILARITY = float(os.getenv("MEMORY_MIN_SIMILARITY", "0.4"))


def _get_chromadb() -> tuple[Any, Any]:
    """延迟导入 ChromaDB，避免未安装时阻塞启动

    模型加载策略（本地优先，解决"每次启动都联网重试"）：
    1. 先用 local_files_only=True 完全离线加载——本地已有缓存则秒开、零网络请求；
       此前直接构造 embedding function 会触发 sentence-transformers 对
       huggingface.co 的版本检查（无网络时表现为 WinError 10060 重试 5 次）。
    2. 仅当本地确无缓存时，才联网下载一次，并打印明确提示。
    3. 将实例预填进 chromadb 的类级模型缓存，其内部构造时直接复用，
       避免二次加载再次触发联网检查。
    """
    import chromadb
    from chromadb.utils import embedding_functions
    from sentence_transformers import SentenceTransformer

    try:
        model = SentenceTransformer(
            EMBED_MODEL, device=EMBED_DEVICE, local_files_only=True
        )
    except Exception:
        print(
            "检测到本地无嵌入模型缓存，首次使用将联网下载 "
            f"({EMBED_MODEL}，约 235MB)，仅此一次...",
            flush=True,
        )
        model = SentenceTransformer(EMBED_MODEL, device=EMBED_DEVICE)

    # 预填 chromadb 类级模型缓存：构造 embedding function 时直接复用该实例
    embedding_functions.SentenceTransformerEmbeddingFunction.models[EMBED_MODEL] = model
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL, device=EMBED_DEVICE
    )

    client = chromadb.PersistentClient(path=MEMORY_DIR)
    return client, emb_fn


# ── 敏感信息检测 ──────────────────────────────────────────────

SENSITIVE_PATTERNS = [
    r'\b\d{11}\b',            # 手机号
    r'\b\d{16,19}\b',         # 银行卡号
    r'(?:密码|口令|secret|password)\s*[是为:：]\s*\S+',  # 密码
    r'(?:身份证|ID|ssn)\s*[是为:：]?\s*\d{17}[\dXx]',     # 身份证
]


def _is_sensitive(text: str) -> bool:
    """检查文本是否包含敏感信息"""
    return any(re.search(p, text, re.IGNORECASE) for p in SENSITIVE_PATTERNS)


# ── 高价值判断 ──────────────────────────────────────────────

# "我不记得了""不知道""随便"等无信息量的回答
_LOW_VALUE_ANSWERS = {
    "不知道", "不清楚", "我不记得了", "随便", "都可以",
    "I don't know", "not sure", "whatever",
}

_HIGH_VALUE_PATTERNS = [
    # 偏好
    r"(?:我|我?喜欢|偏好|倾向于|习惯)\s*(?:用|使用|说|写|吃|喝|住|在)",
    r"(?:更喜欢|更倾向|更习惯)\s*(?:用|使用|说|写|吃|喝)",
    # 个人信息
    r"(?:我|我?叫|我?是|我?在|我?住|我?来自|我?做)",
    r"(?:我的|我?有)\s*(?:工作|公司|学校|专业|年龄|生日|电话|地址|邮箱|微信|QQ)",
    # 任务 / 已完成事项
    r"(?:帮我|请|已经|完成了|部署了|安装了|配置了|写好了|创建了|建了|做了)",
    # 事实性锚点（后续可能引用）
    r"(?:推荐|建议|选择|决定|确认|同意)",
]

# 低价值提问模式：一次性的简单问答
_LOW_VALUE_QUESTIONS = {
    "你好", "hello", "hi", "在吗", "?", "测试", "test",
}

_HIGH_VALUE_ANSWER_MIN_LEN = 10  # 回答少于 10 个字符，大概率是"好的""ok"之类的


def _is_worth_storing(question: str, answer: str) -> bool:
    """判断一问一答是否值得存入长期记忆"""
    q = question.strip().lower()
    a = answer.strip()

    # 回答过短或无价值
    if len(a) < _HIGH_VALUE_ANSWER_MIN_LEN:
        return False
    if a.strip().lower() in _LOW_VALUE_ANSWERS:
        return False

    # 提问是纯寒暄
    if q in _LOW_VALUE_QUESTIONS:
        return False

    # 提问问时间/天气/计算等一次性事实
    if any(kw in q for kw in ["天气", "time", "weather", "几点了", "多少度"]):
        return False

    # 命中高价值模式则存储
    if any(re.search(p, question) for p in _HIGH_VALUE_PATTERNS):
        return True

    # 回答包含结构化信息（列表、代码块、URL）→ 值得存
    if any(kw in answer for kw in ["http://", "https://", "```", "|", "- [ ]"]):
        return True

    # 默认：超过 30 字的有意义回答，可能值得存
    return len(a) > 30


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class MemoryResult:
    """单条检索结果"""
    question: str = ""
    answer: str = ""
    distance: float = 0.0
    timestamp: float = 0.0


# ── 主类 ──────────────────────────────────────────────


class AgentMemory:
    """向量记忆系统"""

    def __init__(self) -> None:
        self._enabled = MEMORY_ENABLED
        self._collection = None
        self._client = None
        self._init_error: str | None = None

        if not self._enabled:
            return

        try:
            self._client, emb_fn = _get_chromadb()
            self._collection = self._client.get_or_create_collection(
                name=MEMORY_COLLECTION,
                embedding_function=emb_fn,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            self._init_error = str(e)
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def init_error(self) -> str | None:
        return self._init_error

    def add(self, question: str, answer: str) -> bool:
        """存储一问一答到向量库（自动过滤低价值和敏感信息）

        Returns:
            True 表示已存储，False 表示被过滤跳过
        """
        if not self._enabled or not self._collection:
            return False

        # 隐私检查
        if _is_sensitive(question) or _is_sensitive(answer):
            return False

        # 价值过滤
        if not _is_worth_storing(question, answer):
            return False

        doc_id = str(uuid.uuid4())
        # e5 系列要求 passage: 前缀
        self._collection.add(
            documents=[f"passage: {answer}"],
            metadatas=[{
                "question": question,
                "timestamp": time.time(),
            }],
            ids=[doc_id],
        )
        return True

    def search(self, query: str, k: int | None = None) -> list[MemoryResult]:
        """语义检索最相似的记忆（自动过滤低分结果）"""
        if not self._enabled or not self._collection:
            return []
        try:
            # e5 系列要求 query: 前缀
            results = self._collection.query(
                query_texts=[f"query: {query}"],
                n_results=(k or MEMORY_TOP_K) * 2,  # 多取一些做过滤
            )
        except Exception:
            return []

        memories: list[MemoryResult] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            dist = distances[i] if distances and i < len(distances) else 0.0
            similarity = 1 - dist
            # 相似度阈值过滤
            if similarity < MEMORY_MIN_SIMILARITY:
                continue

            meta = metadatas[i] if metadatas and i < len(metadatas) else {}
            memories.append(MemoryResult(
                question=meta.get("question", ""),
                answer=documents[i] if documents and i < len(documents) else "",
                distance=dist,
                timestamp=meta.get("timestamp", 0.0),
            ))

        # 按相似度排序，取 top-k
        memories.sort(key=lambda m: m.distance)
        return memories[: (k or MEMORY_TOP_K)]

    @staticmethod
    def _format_time(ts: float) -> str:
        """将时间戳格式化为可读字符串"""
        if not ts:
            return "未知时间"
        try:
            t = time.localtime(ts)
            now = time.localtime()
            days_ago = (time.mktime(now) - time.mktime(t)) / 86400
            if days_ago < 1:
                return "今天"
            if days_ago < 2:
                return "昨天"
            if days_ago < 7:
                return f"{int(days_ago)} 天前"
            return time.strftime("%m-%d", t)
        except Exception:
            return "未知时间"

    def format_context(self, memories: list[MemoryResult]) -> str:
        """将检索结果格式化为 prompt 上下文片段"""
        if not memories:
            return ""
        lines = [
            "\n[以下是你的长期记忆（按相关度排序）]",
            "注意：如果以下记忆与本次对话矛盾，请以本次对话为准。",
        ]
        for i, m in enumerate(memories, 1):
            sim = 1 - m.distance
            when = self._format_time(m.timestamp)
            display_answer = m.answer
            # 去掉 e5 的 passage: 前缀（如存储时已加）
            if display_answer.startswith("passage: "):
                display_answer = display_answer[len("passage: "):]
            lines.append(f"  记忆 #{i} [{when}] (相关度: {sim:.0%}):")
            lines.append(f"    你曾问: {m.question}")
            lines.append(f"    当时回答: {display_answer[:200]}")
        lines.append("[/记忆]\n")
        return "\n".join(lines)

    def clear(self) -> int:
        """清空所有记忆，返回删除条数"""
        if not self._enabled or not self._collection or not self._client:
            return 0
        count = self._collection.count()
        self._client.delete_collection(MEMORY_COLLECTION)
        self._client, emb_fn = _get_chromadb()
        self._collection = self._client.get_or_create_collection(
            name=MEMORY_COLLECTION,
            embedding_function=emb_fn,
            metadata={"hnsw:space": "cosine"},
        )
        return count

    @property
    def count(self) -> int:
        if not self._enabled or not self._collection:
            return 0
        return self._collection.count()


# 全局单例
_memory: AgentMemory | None = None


def get_memory() -> AgentMemory:
    global _memory
    if _memory is None:
        _memory = AgentMemory()
    return _memory
