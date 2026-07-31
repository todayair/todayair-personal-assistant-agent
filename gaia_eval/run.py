"""
GAIA 基准评测 — CLI 入口

使用 GAIA 数据集进行权威评测。

用法:
    python -m gaia_eval.run --gaia                              # 完整 GAIA 评测
    python -m gaia_eval.run --gaia --gaia-levels 1              # 仅 Level 1
    python -m gaia_eval.run --gaia --gaia-max 10                # 仅 10 题尝鲜
    python -m gaia_eval.run --gaia --gaia-no-attach             # 跳过附件题
    python -m gaia_eval.run --gaia --dry-run                    # 预览题数消耗
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from pydantic_ai import Agent
from pydantic_ai.mcp import load_mcp_toolsets
from pydantic_ai.capabilities import WebSearch

from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import Shell
from pydantic_ai_harness.compaction import (
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)

from gaia_eval.gaia_eval import (
    load_gaia_dataset,
    run_gaia,
    save_gaia_report,
    check_auth,
)

# ── 配置 ────────────────────────────────────────────────────

# 确保 stdout 支持 UTF-8（避免 emoji 在 Windows 上出错）
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')  # pyright: ignore
    except Exception:
        pass

MODEL = os.getenv("LLM_MODEL")
assert MODEL, "LLM_MODEL 未设置"

SUMMARY_MODEL = os.getenv("SUMMARY_MODEL") or MODEL
SUMMARY_TARGET_TOKENS = int(os.getenv("SUMMARY_TARGET_TOKENS", "100000"))

# ── Agent 工厂 ─────────────────────────────────────────────

def build_agent(gaia_mode: bool = False):
    """创建评测用 Agent

    Args:
        gaia_mode: GAIA 模式使用更主动的工具调用提示词
    """
    system_prompt = (
        "你是一个能使用多种工具的 AI 助手。面对用户的问题，请主动使用可用工具来获取信息。\n"
        "可用的工具包括:\n"
        "- WebSearch: 联网搜索，用于查找最新信息\n"
        "- FileSystem: 文件读写\n"
        "- Shell: 执行 Python 脚本和系统命令\n"
        "- GitHub 搜索: 搜索代码仓库\n\n"
        "重要准则：\n"
        "1. 如果某个工具调用失败（超时、无结果、报错），不要重试超过 1 次，立即换用其他方案。\n"
        "2. 优先用 WebSearch 代替 GitHub 工具搜索信息，速度更快。\n"
        "3. 文件找不到时，尝试用 Shell 执行 dir/ls 查看当前目录内容后再试。\n"
        "4. 尽量用 Shell 运行 Python 脚本来获取精确计算结果。\n"
        "5. 当需要获取多个独立信息时，同时发起多个工具调用（并行），而不是逐个等待。\n\n"
        "请打印你的每一步思考过程，最后给出最终答案。"
        if gaia_mode else
        "你是一个测试助手，请如实回答用户的每一个问题，保持回答简洁。"
    )

    toolsets = load_mcp_toolsets(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_config.json")
    )

    agent = Agent(  # pyright: ignore[reportCallIssue]
        model=MODEL,
        system_prompt=system_prompt,
        model_settings={'max_retries': 2, 'timeout': 60},  # pyright: ignore[reportArgumentType]
        capabilities=[
            WebSearch(local=True),
            FileSystem(),
            Shell(),
            TieredCompaction(
                tiers=[
                    ClearToolResults(max_tokens=1, keep_pairs=2),
                    SummarizingCompaction(
                        model=SUMMARY_MODEL,
                        max_messages=20,
                        keep_messages=10,
                    ),
                ],
                target_tokens=SUMMARY_TARGET_TOKENS,
            ),
        ],
        toolsets=toolsets,
    )
    return agent


# ── CLI ────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="GAIA 基准评测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览题数消耗，不调 API")
    parser.add_argument("--gaia", action="store_true", help="运行 GAIA 基准评测")
    parser.add_argument("--gaia-levels", type=int, nargs="+", default=None,
                        help="GAIA 难度等级筛选，如 1 2")
    parser.add_argument("--gaia-max", type=int, default=None,
                        help="GAIA 最大题数")
    parser.add_argument("--gaia-no-attach", action="store_true",
                        help="GAIA 跳过带附件的题目")
    return parser


def gaia_dry_run(args):
    """GAIA dry-run preview"""
    print("\n" + "─" * 52)
    print("  GAIA DRY RUN — 仅预览")
    print("─" * 52)

    auth_ok, msg = check_auth()
    if not auth_ok:
        print(f"  {msg}")
        return

    questions = load_gaia_dataset(
        levels=args.gaia_levels,
        max_questions=args.gaia_max,
        skip_attachments=args.gaia_no_attach,
    )
    if not questions:
        return

    total = len(questions)
    l1 = sum(1 for q in questions if q.level == 1)
    l2 = sum(1 for q in questions if q.level == 2)
    l3 = sum(1 for q in questions if q.level == 3)
    with_attach = sum(1 for q in questions if q.file_name)

    print(f"\n  题数: {total}")
    print(f"  难度: L1={l1}  L2={l2}  L3={l3}")
    print(f"  附件: {with_attach} 题")
    print(f"  预估 API: {total} 次调用")
    print(f"  预估耗时: ~{total * 20}s")
    print()

    for q in questions[:5]:
        attach = " [附件]" if q.file_name else ""
        print(f"  [L{q.level}]{attach} {q.question[:70]}")
    if total > 5:
        print(f"  ... 还有 {total - 5} 题")
    print("─" * 52 + "\n")


async def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.dry_run:
        gaia_dry_run(args)
        return

    # ── GAIA 模式 ──
    if args.gaia:
        questions = load_gaia_dataset(
            levels=args.gaia_levels,
            max_questions=args.gaia_max,
            skip_attachments=args.gaia_no_attach,
        )
        if not questions:
            return

        print(f"\n  >> 开始 GAIA 基准评测")
        print(f"  模型: {MODEL}")
        print(f"  题数: {len(questions)}  ({sum(1 for q in questions if q.file_name)} 带附件)")
        print(f"  {'-' * 48}")

        agent = build_agent(gaia_mode=True)
        t0 = time.time()

        async with agent:
            report = await run_gaia(agent, questions)

        elapsed = time.time() - t0

        report.print()
        print(f"总耗时: {elapsed:.1f}s")
        print()

        save_gaia_report(report)
        return

    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
