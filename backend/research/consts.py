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
QUICK_MAX_TOKENS = 75_000
DEEP_MAX_LLM_CALLS = 30
DEEP_MAX_TOKENS = 240_000
# 创建时预算估算口径：deep 每轮固定 4 次调用（假设/规划/代码/反馈），
# quick 每个候选 1 次生成 + 1 次收尾；token 按每次调用粗估，只用于创建时拦明显不够的预算
DEEP_CALLS_PER_LOOP = 4
QUICK_CALLS_PER_CANDIDATE = 1
QUICK_EXTRA_CALLS = 1
# 单次调用 token 估算（实测 9k~17k，思考链长的模型更容易顶到上限）。
# 这是保守下限，用来在创建期展示量级、并在每次调用前预留额度；
# 真实超出的部分按实际结算，不会丢弃已经拿到的产物。
EST_TOKENS_PER_CALL = 12_000

# ---------- LLM 输出上限 ----------
# 输出 token 上限按模型能力配置（会话 cfg 的 llm_max_tokens 优先）。
# 旧值 16384 会被 GLM 的思考链吃满导致 content 为空，默认提到 32768。
DEFAULT_LLM_MAX_TOKENS = 32_768

# ---------- 过程事件 ----------
# 单会话事件保留条数（内存方案的上限；持久化后同样按此裁剪）
EVENTS_DEFAULT_LIMIT = 200
EVENTS_RETENTION = 500

# ---------- 决策硬门（PRD §12 #6）----------
DEFAULT_ICIR_FLOOR = 0.15
DEFAULT_CORR_THRESHOLD = 0.7
# 硬门 3 的因子库对比上限：只取前 N 个可计算因子，避免每个 trial 都全量重算
LIBRARY_CORR_MAX_FACTORS = 8
# quick 的相关性去重沿用现有 llm_miner 默认，避免改变既有挖掘语义
QUICK_DEDUP_CORR = 0.9

# ---------- 轮次去重（deep）----------
# 新候选与任一已终态 trial 因子的最大 |秩相关| 达到该值即判 duplicate：
# 口径与 judge 一致（Spearman，取绝对值，方向翻转也算等价）。
# 0.9 只拦“等价实现”（复制历史因子、只翻转符号/缩放），不误杀同族弱相关变体；
# 会话可用 cfg 的 duplicate_corr_threshold 覆盖。
DUPLICATE_CORR_THRESHOLD = 0.9

# ---------- LLM 调用控制 ----------
# 单次调用硬超时（秒）：与 backend client 的超时同量级，超时后取消请求
DEFAULT_LLM_CALL_TIMEOUT_SECS = 180
# 阶段级硬超时（秒）：code 需要长输出，180s 实测会撞线并吃掉整轮，故单独放宽；
# 其余阶段沿用 180s。会话 cfg 用 llm_<stage>_timeout_secs 覆盖，
# 未配置（None）时沿用全局 llm_call_timeout_secs，全局也未配置则用这里的阶段默认值。
DEFAULT_STAGE_TIMEOUT_SECS: dict[str, float] = {
    "propose": 180.0,
    "plan": 180.0,
    "code": 300.0,
    "feedback": 180.0,
}
# 在飞请求的取消轮询间隔：流式不可用时靠它把 cancel/pause 转成协程取消
LLM_CANCEL_POLL_SECS = 0.25

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
