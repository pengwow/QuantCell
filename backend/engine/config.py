from dataclasses import dataclass, field


@dataclass
class EngineConfig:
    exchange: str = "binance"
    trading_mode: str = "paper"
    risk_config: dict = field(default_factory=dict)
