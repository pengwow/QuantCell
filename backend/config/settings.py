"""
应用配置统一入口（pydantic-settings）

管理所有环境级配置项，支持 .env 文件与环境变量覆盖。
main.py 及生命周期模块统一从这里读取配置，避免散落 os.environ 调用。

使用示例：
    from config.settings import get_settings

    settings = get_settings()
    print(settings.log_level, settings.cors_origin_list)
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置

    环境变量名称对应字段名（大小写不敏感），例如：
    - LOG_LEVEL   -> log_level
    - CORS_ORIGINS -> cors_origins
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "QuantCell API"
    app_version: str = "1.0.0"

    # 日志级别（uvicorn 与业务日志共用）；None 表示未显式配置，回退 config.toml
    log_level: str | None = None

    # CORS 允许来源，逗号分隔；生产环境通过环境变量覆盖
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"

    # 服务监听地址与端口（命令行参数优先，其次此配置）
    default_host: str = "localhost"
    default_port: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取应用配置单例（进程内缓存）"""
    return Settings()


def get_cors_origin_list() -> list[str]:
    """解析 CORS_ORIGINS 为来源列表（逗号分隔，自动忽略空白项）"""
    return [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
