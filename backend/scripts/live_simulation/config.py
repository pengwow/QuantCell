"""
配置管理模块

支持TOML/JSON配置文件、环境变量和命令行参数。
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from pydantic import BaseModel, Field, validator

# 在函数内部导入toml，避免顶部导入错误
def _import_toml():
    try:
        import tomllib
        return tomllib
    except ImportError:
        try:
            import tomli as tomllib
            return tomllib
        except ImportError:
            raise ImportError(
                "tomli package is required. Install with: pip install tomli"
            )


def _import_toml_w():
    try:
        import tomli_w
        return tomli_w
    except ImportError:
        raise ImportError(
            "tomli-w package is required. Install with: pip install tomli-w"
        )


class DataConfig(BaseModel):
    """数据配置"""
    source_type: str = Field("file", description="数据源类型: file, database")
    file_path: Optional[str] = Field(None, description="数据文件路径")
    db_connection: Optional[str] = Field(None, description="数据库连接字符串")
    symbols: List[str] = Field(default_factory=list, description="交易对列表")
    intervals: List[str] = Field(default_factory=lambda: ["1m"], description="时间周期列表")
    start_time: Optional[str] = Field(None, description="开始时间")
    end_time: Optional[str] = Field(None, description="结束时间")
    
    @validator("source_type")
    def validate_source_type(cls, v):
        if v not in ["file", "database"]:
            raise ValueError("source_type must be 'file' or 'database'")
        return v


class PushConfig(BaseModel):
    """数据推送配置"""
    speed: float = Field(1.0, description="推送速度倍率: 0.5, 1.0, 2.0, 5.0, 10.0")
    realtime: bool = Field(False, description="是否实时推送（按实际时间间隔）")
    batch_size: int = Field(1, description="每批推送数据点数")
    batch_interval_ms: int = Field(1000, description="批次间隔毫秒")
    
    @validator("speed")
    def validate_speed(cls, v):
        if v <= 0:
            raise ValueError("speed must be positive")
        return v


class QuantCellConfig(BaseModel):
    """QuantCell连接配置"""
    host: str = Field("localhost", description="QuantCell服务器地址")
    port: int = Field(8000, description="QuantCell服务器端口")
    ws_path: str = Field("/ws", description="WebSocket路径")
    api_key: Optional[str] = Field(None, description="API密钥")
    api_secret: Optional[str] = Field(None, description="API密钥密码")
    use_ssl: bool = Field(False, description="是否使用SSL")
    reconnect_attempts: int = Field(5, description="重连尝试次数")
    reconnect_delay_ms: int = Field(5000, description="重连延迟毫秒")


class WorkerConfig(BaseModel):
    """Worker配置"""
    strategy_path: str = Field(..., description="策略文件路径")
    strategy_class: str = Field("Strategy", description="策略类名")
    strategy_params: Dict[str, Any] = Field(default_factory=dict, description="策略参数")
    symbols: List[str] = Field(default_factory=list, description="Worker订阅的交易对")
    data_types: List[str] = Field(default_factory=lambda: ["kline"], description="数据类型")


class MonitorConfig(BaseModel):
    """监控配置"""
    enabled: bool = Field(True, description="是否启用监控")
    console_output: bool = Field(True, description="是否输出到控制台")
    web_interface: bool = Field(False, description="是否启用Web界面")
    web_port: int = Field(8080, description="Web界面端口")
    update_interval_ms: int = Field(1000, description="更新间隔毫秒")
    metrics_history_size: int = Field(1000, description="指标历史记录大小")


class ExceptionSimulationConfig(BaseModel):
    """异常模拟配置"""
    enabled: bool = Field(False, description="是否启用异常模拟")
    network_delay_ms: int = Field(0, description="网络延迟毫秒")
    network_delay_probability: float = Field(0.0, description="网络延迟概率 0-1")
    disconnect_interval_ms: int = Field(0, description="断开连接间隔毫秒")
    disconnect_duration_ms: int = Field(0, description="断开连接持续时间毫秒")
    data_corruption_probability: float = Field(0.0, description="数据损坏概率 0-1")
    strategy_error_probability: float = Field(0.0, description="策略错误概率 0-1")


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = Field("INFO", description="日志级别")
    file_path: Optional[str] = Field(None, description="日志文件路径")
    max_size_mb: int = Field(100, description="单个日志文件最大大小MB")
    backup_count: int = Field(5, description="备份文件数量")
    format: str = Field(
        "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
        description="日志格式"
    )
    json_format: bool = Field(False, description="是否使用JSON格式")


class SimulationConfig(BaseModel):
    """模拟测试主配置"""
    name: str = Field("simulation", description="测试名称")
    description: str = Field("", description="测试描述")
    duration_hours: float = Field(8.0, description="测试持续时间小时")
    standalone: bool = Field(True, description="独立模式（不连接QuantCell服务）")
    
    data: DataConfig = Field(default_factory=DataConfig)
    push: PushConfig = Field(default_factory=PushConfig)
    quantcell: QuantCellConfig = Field(default_factory=QuantCellConfig)
    workers: List[WorkerConfig] = Field(default_factory=list)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    exception_simulation: ExceptionSimulationConfig = Field(default_factory=ExceptionSimulationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    # 扩展配置
    extra: Dict[str, Any] = Field(default_factory=dict, description="额外配置")
    
    class Config:
        env_prefix = "SIMULATION_"
        case_sensitive = False


def load_config(config_path: Optional[str] = None) -> SimulationConfig:
    """
    加载配置
    
    优先级：命令行参数 > 环境变量 > 配置文件 > 默认值
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        SimulationConfig: 配置对象
    """
    config_dict = {}
    
    # 1. 从配置文件加载
    if config_path and Path(config_path).exists():
        config_dict.update(_load_config_file(config_path))
    
    # 2. 从环境变量加载
    env_config = _load_from_env()
    config_dict.update(env_config)
    
    # 3. 创建配置对象
    return SimulationConfig(**config_dict)


def _load_config_file(config_path: str) -> Dict[str, Any]:
    """从文件加载配置"""
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    if path.suffix == ".toml":
        # TOML格式 - 使用二进制模式
        with open(path, "rb") as f:
            tomllib = _import_toml()
            return tomllib.load(f)
    elif path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        raise ValueError(f"Unsupported config file format: {path.suffix}. Use .toml or .json")


def _load_from_env() -> Dict[str, Any]:
    """从环境变量加载配置"""
    config = {}
    
    # QuantCell连接配置
    if host := os.getenv("SIMULATION_QUANTCELL_HOST"):
        config.setdefault("quantcell", {})["host"] = host
    if port := os.getenv("SIMULATION_QUANTCELL_PORT"):
        config.setdefault("quantcell", {})["port"] = int(port)
    if api_key := os.getenv("SIMULATION_QUANTCELL_API_KEY"):
        config.setdefault("quantcell", {})["api_key"] = api_key
    if api_secret := os.getenv("SIMULATION_QUANTCELL_API_SECRET"):
        config.setdefault("quantcell", {})["api_secret"] = api_secret
    
    # 数据配置
    if data_path := os.getenv("SIMULATION_DATA_PATH"):
        config.setdefault("data", {})["file_path"] = data_path
    if symbols := os.getenv("SIMULATION_SYMBOLS"):
        config.setdefault("data", {})["symbols"] = symbols.split(",")
    
    # 推送配置
    if speed := os.getenv("SIMULATION_PUSH_SPEED"):
        config.setdefault("push", {})["speed"] = float(speed)
    
    # Worker配置
    if strategy_path := os.getenv("SIMULATION_STRATEGY_PATH"):
        config.setdefault("workers", [{}])
        config["workers"][0]["strategy_path"] = strategy_path
    
    return config


def _remove_none_values(obj: Any) -> Any:
    """递归移除字典中的None值"""
    if isinstance(obj, dict):
        return {k: _remove_none_values(v) for k, v in obj.items() if v is not None}
    elif isinstance(obj, list):
        return [_remove_none_values(item) for item in obj]
    else:
        return obj


def save_config(config: SimulationConfig, config_path: str):
    """
    保存配置到文件
    
    Args:
        config: 配置对象
        config_path: 配置文件路径
    """
    path = Path(config_path)
    config_dict = config.dict()
    
    if path.suffix == ".toml":
        # TOML格式 - 移除None值
        tomli_w = _import_toml_w()
        clean_dict = _remove_none_values(config_dict)
        with open(path, "wb") as f:
            tomli_w.dump(clean_dict, f)
    elif path.suffix == ".json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Unsupported config file format: {path.suffix}. Use .toml or .json")


def create_default_config(config_path: str):
    """
    创建默认配置文件
    
    Args:
        config_path: 配置文件路径
    """
    default_config = SimulationConfig(
        name="default_simulation",
        description="默认模拟测试配置",
        data=DataConfig(
            source_type="file",
            symbols=["BTCUSDT", "ETHUSDT"],
            intervals=["1m", "5m"],
        ),
        push=PushConfig(
            speed=1.0,
            realtime=False,
        ),
        quantcell=QuantCellConfig(
            host="localhost",
            port=8000,
        ),
        workers=[
            WorkerConfig(
                strategy_path="scripts/live_simulation/strategies/test_strategy.py",
                strategy_class="TestStrategy",
                symbols=["BTCUSDT"],
            )
        ],
        monitor=MonitorConfig(
            enabled=True,
            console_output=True,
        ),
    )
    
    save_config(default_config, config_path)


# 默认配置实例
default_config = SimulationConfig()
