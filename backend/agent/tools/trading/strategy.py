"""策略工具 - 管理交易策略"""

from typing import Any

from ..base import Tool


class ListStrategiesTool(Tool):
    """列出所有策略"""

    name = "list_strategies"
    description = "列出系统中所有可用的交易策略。"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> str:
        try:
            from strategy.models import Strategy
            from collector.db.database import SessionLocal
            
            db = SessionLocal()
            try:
                strategies = db.query(Strategy).all()
                if not strategies:
                    return "系统中暂无策略"
                
                lines = ["可用策略列表:\n"]
                for s in strategies:
                    lines.append(
                        f"ID: {s.id}, 名称: {s.name}, "
                        f"类型: {s.strategy_type or 'N/A'}, "
                        f"状态: {'已激活' if s.is_active else '未激活'}"
                    )
                return "\n".join(lines)
            finally:
                db.close()
        except Exception as e:
            return f"错误: 获取策略列表失败: {e}"


class GetStrategyDetailTool(Tool):
    """获取策略详情"""

    name = "get_strategy_detail"
    description = "获取指定策略的详细信息。"
    parameters = {
        "type": "object",
        "properties": {
            "strategy_id": {"type": "integer", "description": "策略 ID"},
        },
        "required": ["strategy_id"],
    }

    async def execute(self, strategy_id: int, **kwargs: Any) -> str:
        try:
            from strategy.models import Strategy
            from collector.db.database import SessionLocal
            
            db = SessionLocal()
            try:
                strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
                if not strategy:
                    return f"策略 ID {strategy_id} 不存在"
                
                return (
                    f"策略详情:\n"
                    f"ID: {strategy.id}\n"
                    f"名称: {strategy.name}\n"
                    f"描述: {strategy.description or 'N/A'}\n"
                    f"类型: {strategy.strategy_type or 'N/A'}\n"
                    f"状态: {'已激活' if strategy.is_active else '未激活'}\n"
                    f"创建时间: {strategy.created_at}\n"
                    f"更新时间: {strategy.updated_at}"
                )
            finally:
                db.close()
        except Exception as e:
            return f"错误: 获取策略详情失败: {e}"


class RunBacktestTool(Tool):
    """运行回测"""

    name = "run_backtest"
    description = "对指定策略运行回测。"
    parameters = {
        "type": "object",
        "properties": {
            "strategy_id": {"type": "integer", "description": "策略 ID"},
            "symbol": {"type": "string", "description": "交易对，如 BTCUSDT"},
            "timeframe": {"type": "string", "description": "时间周期", "default": "1h"},
            "start_date": {"type": "string", "description": "开始日期 (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "结束日期 (YYYY-MM-DD)"},
        },
        "required": ["strategy_id", "symbol"],
    }

    async def execute(
        self,
        strategy_id: int,
        symbol: str,
        timeframe: str = "1h",
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any
    ) -> str:
        try:
            from backtest.service import BacktestService
            
            service = BacktestService()
            result = await service.run_backtest(
                strategy_id=strategy_id,
                symbol=symbol.upper(),
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
            )
            
            if not result:
                return "回测执行失败"
            
            return (
                f"回测结果:\n"
                f"总收益率: {result.get('total_return', 'N/A')}%\n"
                f"年化收益率: {result.get('annual_return', 'N/A')}%\n"
                f"最大回撤: {result.get('max_drawdown', 'N/A')}%\n"
                f"夏普比率: {result.get('sharpe_ratio', 'N/A')}\n"
                f"交易次数: {result.get('total_trades', 'N/A')}"
            )
        except Exception as e:
            return f"错误: 回测执行失败: {e}"
