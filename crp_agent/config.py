"""全局路径与常量。

所有模块统一从这里取路径，避免相对路径在不同工作目录下失效。
"""

from pathlib import Path

# ---------------------------------------------------------------- 路径
ROOT = Path(__file__).resolve().parent          # crp_agent/
PROJECT = ROOT.parent                            # 仓库根目录

DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RUNS_DIR = ROOT / "runs"
FIG_DIR = ROOT / "figures"

for _d in (DATA_DIR, CACHE_DIR, RUNS_DIR, FIG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 不变量
# 向量顺序固定，全项目共用。改动此处须同步更新报告表 1。
INVARIANTS = ["n", "m", "Delta", "delta", "alpha", "omega", "chi", "nu", "rho"]

# 中文名，用于图表标注
INVARIANT_CN = {
    "n": "顶点数",
    "m": "边数",
    "Delta": "最大度",
    "delta": "最小度",
    "alpha": "独立数",
    "omega": "团数",
    "chi": "色数",
    "nu": "匹配数",
    "rho": "谱半径",
}

# NP-难的不变量：在规模较大时需要特殊处理
NP_HARD = {"alpha", "omega", "chi"}

# ---------------------------------------------------------------- 数据集
# 完全枚举的阶数上界。n=8 共 12346 张图，n=9 共 274668 张。
EXHAUSTIVE_MAX_N = 8

# 随机采样的阶数
SAMPLED_N = [9, 10, 11, 12]

# 随机采样每个阶数的图数
SAMPLE_PER_N = 4000

# 随机图的边概率列表
SAMPLE_P = [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85]

# 随机数种子，保证可复现
SEED = 20261120
