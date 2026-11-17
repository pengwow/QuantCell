"""命名契约词汇表只读端点 — 命名审计 P2-5（原始条目 A-4）

GET /api/v1/vocab：输出 backend/vocab.py 的结构化词条（canonical/banned/reserved）
与方向枚举值域。前端类型生成脚本（backend/scripts/export_vocab_types.py）与
词汇表 UI 消费同一事实源；无敏感信息，不挂鉴权（同 capabilities 端点）。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from common.schemas import ApiResponse
from vocab import VOCAB_DOMAINS, VOCAB_ENUMS

router = APIRouter(prefix="/api/v1/vocab", tags=["Vocab"])


class VocabTermOut(BaseModel):
    term: str = Field(description="词条（canonical 词 / 禁用词 / 保留词）")
    kind: str = Field(description="canonical | banned | reserved")
    note: str = Field(description="边界裁决全文")


class VocabDomainOut(BaseModel):
    name: str = Field(description="词汇域名（direction/account/symbol/...）")
    terms: list[VocabTermOut] = Field(description="词条集")


@router.get(
    "",
    summary="获取命名契约词汇表",
    description="输出命名审计定档的结构化词条与方向枚举值域（单一事实源 backend/vocab.py），"
    "供前端类型生成、词汇表展示与 CI 对账消费",
)
async def read_vocab() -> ApiResponse:
    banned = sorted(t.term for d in VOCAB_DOMAINS for t in d.terms if t.kind == "banned")
    data = {
        "domains": [{"name": d.name, "terms": [t._asdict() for t in d.terms]} for d in VOCAB_DOMAINS],
        "enums": {k: list(v) for k, v in VOCAB_ENUMS.items()},
        "banned_terms": banned,
    }
    return ApiResponse(code=0, message="ok", data=data)
