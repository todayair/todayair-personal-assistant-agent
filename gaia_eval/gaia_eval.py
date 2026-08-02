"""
GAIA (General AI Assistants) 评测集成

使用 GAIA 数据集对 Agent 进行标准化评测。
数据集包含 165 道验证题（Level 1-3），每题有唯一标准答案。

评分规则（官方标准）：
  - Agent 的回答与 Final answer 精确匹配 → 通过
  - 未命中 → 不通过
  - 总分 = 通过数 / 总题数 × 100

使用前需要：
  1. 注册 HuggingFace: https://huggingface.co/join
  2. 接受 GAIA 条款: https://huggingface.co/datasets/gaia-benchmark/GAIA
  3. 生成 Token: https://huggingface.co/settings/tokens
  4. 设置环境变量 HF_TOKEN 或运行 huggingface-cli login
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# ── 依赖导入（可降级） ──────────────────────────────────────

_has_datasets = False
load_dataset: Any = None
try:
    from datasets import load_dataset
    _has_datasets = True
except ImportError:
    pass

_has_hub = False
get_token: Any = None
hf_hub_download: Any = None
try:
    from huggingface_hub import get_token, hf_hub_download
    _has_hub = True
except ImportError:
    pass


# ======================================================================
# 数据模型
# ======================================================================

@dataclass
class GaiaQuestion:
    task_id: str
    question: str
    level: int
    true_answer: str
    file_name: str | None = None
    file_path: str | None = None
    attachment_dir: str | None = None     # 附件的本地目录
    attachment_repo_path: str | None = None  # 附件在 HF 仓库中的路径


@dataclass
class GaiaResult:
    task_id: str
    question: str
    level: int
    true_answer: str
    agent_answer: str
    passed: bool           # 精确匹配
    near_miss: bool        # 接近正确但未命中
    timing: float          # 耗时(秒)
    error: str | None = None
    agent_responses: list[str] = field(default_factory=list)


@dataclass
class GaiaReport:
    timestamp: str
    num_questions: int
    num_passed: int
    num_near_miss: int
    accuracy: float            # 0-100
    l1_accuracy: float | None
    l2_accuracy: float | None
    l3_accuracy: float | None
    avg_timing: float
    results: list[GaiaResult]
    config: dict[str, object]

    def print(self):
        W = 56
        print("\n" + "█" * W)
        print(f"  GAIA 基准评测报告")
        print(f"  {'=' * 44}")
        print(f"  时间: {self.timestamp}")
        model_text = str(self.config.get("model", "?"))
        details = self.config.get("model_details")
        if details:
            model_text += "  (" + ", ".join(f"{k}={v}" for k, v in details.items()) + ")"
        print(f"  模型: {model_text}")
        print(f"  {'=' * 44}")
        print(f"  ⭐ 准确率: {self.accuracy:.1f}%  ({self.num_passed}/{self.num_questions})")
        print(f"  {'=' * 44}")
        print()

        # 按难度
        if self.l1_accuracy is not None:
            print(f"  Level 1: {self.l1_accuracy:.1f}%  ({self.num_passed if self.l1_accuracy else 0}/{self.num_questions})")
        if self.l2_accuracy is not None:
            print(f"  Level 2: {self.l2_accuracy:.1f}%")
        if self.l3_accuracy is not None:
            print(f"  Level 3: {self.l3_accuracy:.1f}%")
        print(f"  平均耗时: {self.avg_timing:.1f}s/题")
        if self.num_near_miss > 0:
            print(f"  接近正确: {self.num_near_miss} 题")
        print()

        # 逐题结果
        print(f"  ┌─ 逐题详情 ─────────────────────────────┐")
        passed = 0
        for r in self.results:
            icon = "✓" if r.passed else ("△" if r.near_miss else "✗")
            ans_preview = (r.agent_answer or "")[:40].replace("\n", " ")
            print(f"  │ {icon} [{r.level}] {r.task_id:12s} {r.timing:5.1f}s")
            if not r.passed:
                q_preview = r.question[:50].replace("\n", " ")
                print(f"  │       Q: {q_preview}")
                print(f"  │       答: {ans_preview}")
                print(f"  │       标: {r.true_answer[:50]}")
                if r.near_miss:
                    print(f"  │       (接近正确)")
        print(f"  └──────────────────────────────────────────┘")
        print()

        # 排行参考
        print(f"  参考排行 (GAIA Leaderboard 已知分数):")
        print(f"    GPT-4o:         ~44%")
        print(f"    GPT-4-turbo:    ~32%")
        print(f"    Claude 3.5:     ~35%")
        print(f"    人类:           ~92%")
        print()
        print("█" * W + "\n")


# ======================================================================
# 认证与数据集加载
# ======================================================================

def check_auth() -> tuple[bool, str]:
    """检查 HuggingFace 认证状态"""
    token = None
    if _has_hub:
        token = get_token()
    if token is None:
        token = os.environ.get("HF_TOKEN")
    if token is None:
        return False, (
            "未找到 HuggingFace Token。请按以下步骤操作:\n"
            "  1. 注册/登录 https://huggingface.co\n"
            "  2. 接受 GAIA 条款: https://huggingface.co/datasets/gaia-benchmark/GAIA\n"
            "  3. 生成 Token: https://huggingface.co/settings/tokens\n"
            "  4. 设置环境变量: set HF_TOKEN=hf_xxxxx  (Windows)\n"
            '     或: huggingface-cli login'
        )
    return True, "已认证"


def _download_attachment(q: GaiaQuestion) -> str | None:
    """把附件从 HF 仓库下载到本地 .attachments/ 目录

    Args:
        q: 题目对象（需含 attachment_repo_path）

    Returns:
        本地绝对路径；下载失败返回 None
    """
    if not q.attachment_repo_path:
        return None
    if not _has_hub or hf_hub_download is None:
        print("  错误: 需要安装 huggingface_hub 才能下载附件")
        return None
    try:
        cache_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            ".attachments",
        )
        os.makedirs(cache_dir, exist_ok=True)
        local = hf_hub_download(
            repo_id="gaia-benchmark/GAIA",
            filename=q.attachment_repo_path,
            repo_type="dataset",
            local_dir=cache_dir,
        )
        return os.path.abspath(local)
    except Exception as e:
        print(f"  附件下载失败 {q.file_name}: {e}", flush=True)
        return None


def load_gaia_dataset(
    levels: list[int] | None = None,
    max_questions: int | None = None,
    skip_attachments: bool = False,
    cache_dir: str | None = None,
    download_attachments: bool = True,
) -> list[GaiaQuestion]:
    """加载 GAIA 验证集

    Args:
        levels: 筛选难度等级，如 [1, 2] 只加载 Level 1 和 2
        max_questions: 最多加载题目数
        skip_attachments: 跳过带附件的题目
        cache_dir: 缓存目录
        download_attachments: 是否把附件下载到本地（默认 True）
    """
    if not _has_datasets:
        print("  错误: 需要安装 datasets 库: pip install datasets")
        return []

    auth_ok, msg = check_auth()
    if not auth_ok:
        print(f"\n  {msg}\n")
        return []

    print(f"  正在加载 GAIA 数据集...", flush=True)

    try:
        ds = load_dataset(
            "gaia-benchmark/GAIA",
            "2023_all",
            split="validation",
            cache_dir=cache_dir,
        )
    except Exception as e:
        print(f"  加载失败: {e}")
        print("  请确认已接受 GAIA 条款: https://huggingface.co/datasets/gaia-benchmark/GAIA")
        return []

    questions: list[GaiaQuestion] = []
    total = len(ds)
    skipped_attach = 0
    skipped_level = 0

    for row in ds:
        q_level = row["Level"]

        # 按难度筛选
        if levels and q_level not in levels:
            skipped_level += 1
            continue

        # 是否跳过附件题
        has_attachment = bool(row.get("file_name"))
        if skip_attachments and has_attachment:
            skipped_attach += 1
            continue

        # 附件在 HF 仓库中的原始路径（如 2023/validation/xxx.xlsx）
        repo_path = row.get("file_path") or None

        q = GaiaQuestion(
            task_id=row["task_id"],
            question=row["Question"],
            level=q_level,
            true_answer=row["Final answer"],
            file_name=row.get("file_name") or None,
            file_path=None,
            attachment_dir=None,
            attachment_repo_path=repo_path,
        )

        # 下载附件到本地（避免 Agent 因找不到附件而空转卡死）
        if q.file_name and download_attachments:
            local = _download_attachment(q)
            if local:
                q.file_path = local
                q.attachment_dir = os.path.dirname(local)
            else:
                print(f"  警告: 附件下载失败，该题将被跳过: {q.task_id}", flush=True)

        questions.append(q)

        if max_questions and len(questions) >= max_questions:
            break

    print(f"  加载完成: {len(questions)} 题", flush=True)
    if skipped_level:
        print(f"  跳过(难度筛选): {skipped_level} 题", flush=True)
    if skipped_attach:
        print(f"  跳过(附件): {skipped_attach} 题", flush=True)

    return questions


# ======================================================================
# GAIA 评分器
# ======================================================================

def _normalize(text: str) -> str:
    """GAIA 标准答案归一化"""
    text = text.strip()
    # 去除首尾引号
    text = text.strip('"\'"\'')
    # 统一空白
    text = re.sub(r'\s+', ' ', text)
    # 统一大小写（英语题）
    text = text.lower()
    return text.strip()


def _match_answer(agent_answer: str, true_answer: str) -> tuple[bool, bool]:
    """
    判断 Agent 回答是否匹配标准答案。
    返回 (exact_match, near_match)
    """
    if not agent_answer or not true_answer:
        return False, False

    agent_norm = _normalize(agent_answer)
    true_norm = _normalize(true_answer)

    # 精确匹配
    if agent_norm == true_norm:
        return True, True

    # 标准答案在回答中（Agent 可能回答多余文字）
    if true_norm in agent_norm:
        return True, True

    # 接近匹配：提取回答中最后一行的关键部分
    lines = [l.strip() for l in agent_answer.strip().split("\n") if l.strip()]
    last_line = _normalize(lines[-1]) if lines else ""

    if true_norm == last_line:
        return True, True

    if true_norm in last_line:
        return True, True

    return False, False


def _levenshtein_ratio(a: str, b: str) -> float:
    """编辑距离相似度（用于 'near match' 判断）"""
    if not a or not b:
        return 0.0
    a, b = _normalize(a), _normalize(b)
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if a[i-1] == b[j-1] else 1
            dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + cost)
    return 1 - dp[n][m] / max(n, m)


def _is_near_match(agent_answer: str, true_answer: str) -> bool:
    """判断是否接近正确（宽松匹配）"""
    agent_norm = _normalize(agent_answer)
    true_norm = _normalize(true_answer)

    if not agent_norm or not true_norm:
        return False

    # 编辑距离 > 0.8
    if _levenshtein_ratio(agent_norm, true_norm) > 0.8:
        return True

    # 关键数字/关键词包含
    agent_words = set(agent_norm.split())
    true_words = set(true_norm.split())
    if len(true_words) > 0:
        overlap = len(agent_words & true_words) / len(true_words)
        if overlap > 0.7:
            return True

    return False


# ======================================================================
# 评测运行器
# ======================================================================

async def run_gaia(
    agent_ctx,
    questions: list[GaiaQuestion],
    max_concurrent: int = 1,       # GAIA 题需要串行（工具调用可能有状态）
    verbose: bool = False,
    timeout_per_question: float = 420.0,   # 单题超时秒数，超时记为失败继续下一题
) -> GaiaReport:
    """运行 GAIA 评测

    Args:
        agent_ctx: Agent 实例（已进入 async with 上下文）
        questions: GAIA 题目列表
        max_concurrent: 并发数（GAIA 建议串行）
        verbose: 详细输出
        timeout_per_question: 单题超时秒数，超时记为失败继续下一题（默认 420）
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    results: list[GaiaResult] = []
    config = _capture_config(agent_ctx)

    total = len(questions)
    print(f"\n  开始 GAIA 评测: {total} 题")
    print(f"  {'─' * 48}", flush=True)

    for idx, q in enumerate(questions, 1):
        t0 = time.time()
        error = None
        agent_responses: list[str] = []

        print(f"  [{idx:3d}/{total}] L{q.level} {q.task_id:12s} ...", end=" ", flush=True)

        # 构造 Agent 输入：带上附件提示
        prompt = q.question
        if q.file_name and q.file_path:
            prompt += (
                f"\n\n（附件已下载到本地: {q.file_path}\n"
                "请直接用 Shell/FileSystem 工具读取该文件，不要联网搜索文件名）"
            )
        elif q.file_name:
            # 附件下载失败：直接判失败，不浪费模型调用
            results.append(GaiaResult(
                task_id=q.task_id,
                question=q.question,
                level=q.level,
                true_answer=q.true_answer,
                agent_answer="<SKIP: 附件下载失败>",
                passed=False,
                near_miss=False,
                timing=0.0,
                error="附件下载失败，题目被跳过",
                agent_responses=[],
            ))
            print("✗  0.0s (附件下载失败)", flush=True)
            continue

        try:
            # 发送问题（单题全局超时，防止工具/网络卡死整场评测）
            history = None
            response = await asyncio.wait_for(
                agent_ctx.run(prompt, message_history=history),
                timeout=timeout_per_question,
            )
            agent_responses.append(response.output)
            agent_answer = response.output
        except asyncio.TimeoutError:
            error = f"超过单题时限 {timeout_per_question:.0f}s"
            agent_answer = f"<TIMEOUT: {error}>"
            print(f"⏱  超时 {timeout_per_question:.0f}s", flush=True)
        except Exception as e:
            error = str(e)
            agent_answer = f"<ERROR: {e}>"

        elapsed = time.time() - t0

        # 评分
        passed, near = _match_answer(agent_answer, q.true_answer)
        if not passed:
            near = _is_near_match(agent_answer, q.true_answer)
        else:
            near = True

        results.append(GaiaResult(
            task_id=q.task_id,
            question=q.question,
            level=q.level,
            true_answer=q.true_answer,
            agent_answer=agent_answer,
            passed=passed,
            near_miss=(near and not passed),
            timing=elapsed,
            error=error,
            agent_responses=agent_responses,
        ))

        icon = "✓" if passed else ("△" if near else "✗")
        print(f"{icon}  {elapsed:.1f}s", flush=True)

        if verbose and not passed:
            print(f"         答案: {agent_answer[:80]}", flush=True)
            print(f"         标准: {q.true_answer[:80]}", flush=True)

    # 统计
    num_passed = sum(1 for r in results if r.passed)
    num_near = sum(1 for r in results if r.near_miss)

    accuracy = (num_passed / total * 100) if total > 0 else 0.0
    avg_timing = sum(r.timing for r in results) / total if total > 0 else 0.0

    # 按难度
    def level_acc(l: int) -> float | None:
        l_results = [r for r in results if r.level == l]
        if not l_results:
            return None
        return sum(1 for r in l_results if r.passed) / len(l_results) * 100

    l1_acc = level_acc(1)
    l2_acc = level_acc(2)
    l3_acc = level_acc(3)

    return GaiaReport(
        timestamp=timestamp,
        num_questions=total,
        num_passed=num_passed,
        num_near_miss=num_near,
        accuracy=accuracy,
        l1_accuracy=l1_acc,
        l2_accuracy=l2_acc,
        l3_accuracy=l3_acc,
        avg_timing=avg_timing,
        results=results,
        config=config,
    )


def _capture_config(agent_ctx) -> dict[str, object]:
    config = {}
    try:
        model_obj = getattr(agent_ctx, "model", None)
        config["model"] = str(model_obj) if model_obj is not None else "?"
        details = {}
        for attr in ("model_name", "name", "base_url"):
            try:
                v = getattr(model_obj, attr, None)
                if v:
                    details[attr] = str(v)
            except Exception:
                pass
        if details:
            config["model_details"] = details
    except Exception:
        config["model"] = "?"
    try:
        caps = getattr(agent_ctx, "capabilities", [])
        config["capabilities"] = [type(c).__name__ for c in caps]
    except Exception:
        config["capabilities"] = []
    return config


# ======================================================================
# 统计对比工具
# ======================================================================

def print_gaia_history():
    """查看之前保存的 GAIA 评测历史（TODO）"""
    print("GAIA 历史记录功能即将推出")


def save_gaia_report(report: GaiaReport, filepath: str | None = None):
    """保存 GAIA 报告到 JSON 文件（results/ 子文件夹）"""
    if filepath is None:
        report_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "results",
        )
        os.makedirs(report_dir, exist_ok=True)
        filepath = os.path.join(
            report_dir,
            f"_gaia_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        )

    data = {
        "timestamp": report.timestamp,
        "num_questions": report.num_questions,
        "num_passed": report.num_passed,
        "num_near_miss": report.num_near_miss,
        "accuracy": round(report.accuracy, 2),
        "l1_accuracy": round(report.l1_accuracy, 2) if report.l1_accuracy is not None else None,
        "l2_accuracy": round(report.l2_accuracy, 2) if report.l2_accuracy is not None else None,
        "l3_accuracy": round(report.l3_accuracy, 2) if report.l3_accuracy is not None else None,
        "avg_timing": round(report.avg_timing, 2),
        "config": report.config,
        "results": [
            {
                "task_id": r.task_id,
                "level": r.level,
                "passed": r.passed,
                "near_miss": r.near_miss,
                "timing": round(r.timing, 2),
                "error": r.error,
            }
            for r in report.results
        ],
    }

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n  报告已保存: {filepath}", flush=True)
    return filepath
