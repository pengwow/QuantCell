from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from utils.logger import get_logger, LogType
from . import crud

logger = get_logger(__name__, LogType.APPLICATION)


class TradingStatsService:

    def __init__(self, db: Session):
        self.db = db

    def get_trading_summary(self, worker_id: int) -> dict:
        return crud.get_trading_summary(self.db, worker_id)

    def get_position_summary(self, worker_id: int) -> dict:
        from .models import WorkerPosition

        positions = self.db.query(WorkerPosition).filter(
            WorkerPosition.worker_id == worker_id,
            WorkerPosition.status == "OPEN"
        ).all()

        total_positions = len(positions)
        long_positions = sum(1 for p in positions if p.side == "LONG")
        short_positions = sum(1 for p in positions if p.side == "SHORT")
        total_value = sum(p.quantity * (p.current_price or p.entry_price or 0) for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl or 0 for p in positions)
        total_margin_used = sum(p.margin_used or 0 for p in positions)

        return {
            "total_positions": total_positions,
            "long_positions": long_positions,
            "short_positions": short_positions,
            "total_value": round(total_value, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_margin_used": round(total_margin_used, 2),
            "positions": [p.to_dict() for p in positions],
        }

    def get_pnl_distribution(self, worker_id: int) -> dict:
        return crud.get_pnl_distribution(self.db, worker_id)

    def get_trade_history_chart(self, worker_id: int, days: int = 30) -> dict:
        return crud.get_trade_history_chart(self.db, worker_id, days)
