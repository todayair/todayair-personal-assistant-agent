"""
gaia_eval — GAIA 基准评测

使用 GAIA 数据集进行权威评测。

用法:
    python -m gaia_eval.run --gaia                          # 跑完整 GAIA 评测
    python -m gaia_eval.run --gaia --gaia-levels 1          # 仅 Level 1 题
    python -m gaia_eval.run --gaia --gaia-max 10            # 仅 10 题尝鲜
    python -m gaia_eval.run --gaia --gaia-no-attach         # 跳过带附件题
"""
