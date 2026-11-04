"""研究会话默认参数集中配置。

PRD §12 中尚未拍板的默认值全部收敛在这里，业务代码只引用常量、不写魔法数，
后续单点修改即可（例如成本上限、数据窗口、硬门阈值）。
"""

from __future__ import annotations

# ---------- 数据窗口 ----------
MIN_WINDOW_DAYS = 30  # PRD §12 #5：窗口最小跨度（建议 ≥30 天）
MAX_SYMBOLS = 20  # PRD §12 #5：单会话最多品种数
MAX_LOOP_N = 10

# ---------- 候选与轮次 ----------
DEFAULT_QUICK_CANDIDATES = 4  # quick 单轮候选数，沿用现有挖掘默认
DEFAULT_DEEP_CANDIDATES = 2  # deep 每轮候选数（P0 每次只落 1 条 trial）
DEFAULT_DEEP_LOOPS = 3
DEFAULT_TASKS_PER_LOOP = 2
DEFAULT_REPAIR_ROUNDS = 2  # 代码生成/评估失败后的自动重写轮数（P1 自修复内环）
MAX_REPAIR_ROUNDS = 5  # 单 trial 最多修复轮数，防止无限烧钱

# ---------- 成本上限（PRD §12 #3）----------
QUICK_MAX_LLM_CALLS = 6
QUICK_MAX_TOKENS = 40_000
DEEP_MAX_LLM_CALLS = 30
DEEP_MAX_TOKENS = 200_000
# 创建时预算估算口径：deep 每轮固定 4 次调用（假设/规划/代码/反馈），
# quick 每个候选 1 次生成 + 1 次收尾；token 按每次调用粗估，只用于创建时拦明显不够的预算
DEEP_CALLS_PER_LOOP = 4
QUICK_CALLS_PER_CANDIDATE = 1
QUICK_EXTRA_CALLS = 1
EST_TOKENS_PER_CALL = 3_000

# ---------- 决策硬门（PRD §12 #6）----------
DEFAULT_ICIR_FLOOR = 0.15
DEFAULT_CORR_THRESHOLD = 0.7
# 硬门 3 的因子库对比上限：只取前 N 个可计算因子，避免每个 trial 都全量重算
LIBRARY_CORR_MAX_FACTORS = 8
# quick 的相关性去重沿用现有 llm_miner 默认，避免改变既有挖掘语义
QUICK_DEDUP_CORR = 0.9

# ---------- 采样与评估 ----------
QUICK_TEMPERATURE = 0.8  # §6.5：quick 沿用现有挖掘温度
DEEP_TEMPERATURE = 0.2  # §9：deep 固定低温便于复现
DEFAULT_TEST_RATIO = 0.3
DEFAULT_WF_FOLDS = 0

# ---------- 控制面 ----------
MAX_ACTIVE_SESSIONS = 2  # 同一用户同时 running 会话上限，超出 429
DEEP_JOB_WORKERS = 2  # deep 独立线程池（PRD §9）
EVENTS_DEFAULT_LIMIT = 500
KNOWLEDGE_BLOCK_THRESHOLD = 3  # 失败签名连续 3 次即 blocked（P1 短路生效）
