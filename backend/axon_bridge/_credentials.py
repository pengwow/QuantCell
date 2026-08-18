"""axon_quant LLM/Exchange 凭证集中管理(QuantCell 增值)。

所有 Exchange/LLM 调用统一从 `credentials` 单例读取,避免散落 os.environ 读取。
P3 接入 axon-harness 后改为从 Vault 拉取。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AxonQuantCredentials(BaseSettings):
    """axon_quant 凭证配置。"""

    # LLM
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    local_llm_endpoint: str | None = None

    # Exchange
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    okx_api_key: str | None = None
    okx_api_secret: str | None = None
    okx_passphrase: str | None = None

    # axon-harness(P3 集成)
    enable_rbac: bool = False

    model_config = SettingsConfigDict(
        env_prefix="AXON_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# 全局单例
credentials = AxonQuantCredentials()
