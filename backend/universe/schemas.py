"""标的池 Pydantic 请求模型（P2-03）。"""

from pydantic import BaseModel, Field, model_validator


class UniverseCreateRequest(BaseModel):
    """创建标的池：初始成分可选，建池后也可再增删。"""

    name: str = Field(min_length=1, max_length=100, description="池名称（唯一）")
    description: str | None = Field(default=None, max_length=500, description="描述")
    symbols: list[str] = Field(default_factory=list, description="初始成分列表，可选")


class UniverseUpdateRequest(BaseModel):
    """更新标的池：名称/描述至少提供其一。"""

    name: str | None = Field(default=None, min_length=1, max_length=100, description="新名称")
    description: str | None = Field(default=None, max_length=500, description="新描述")

    @model_validator(mode="after")
    def _at_least_one(self) -> UniverseUpdateRequest:
        if self.name is None and self.description is None:
            raise ValueError("name 与 description 至少提供其一")
        return self


class UniverseMembersRequest(BaseModel):
    """成分增删请求。"""

    symbols: list[str] = Field(min_length=1, description="要加入/移出的交易对列表")
