"""策略工具 - 薄封装，调用CLI层"""

import json
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
        from cli.strategy import list_strategies
        return list_strategies()


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
        from cli.strategy import get_strategy_detail
        return get_strategy_detail(strategy_id)


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


class GenerateStrategyTool(Tool):
    """生成策略"""

    name = "generate_strategy"
    description = "根据自然语言描述生成量化策略代码。生成后自动验证并保存到策略目录。"
    parameters = {
        "type": "object",
        "properties": {
            "requirement": {"type": "string", "description": "策略需求描述，如'双均线交叉策略，快线10日，慢线30日'"},
            "strategy_name": {"type": "string", "description": "策略名称，用于文件命名"},
            "indicators": {"type": "string", "description": "自定义指标配置（可选），JSON格式"},
        },
        "required": ["requirement", "strategy_name"],
    }

    param_template = {}

    async def execute(
        self,
        requirement: str,
        strategy_name: str,
        indicators: str | None = None,
        **kwargs: Any,
    ) -> str:
        from cli.strategy import generate_strategy
        return generate_strategy(requirement, strategy_name, indicators)


class AnalyzeBacktestResultTool(Tool):
    """分析回测结果"""

    name = "analyze_backtest_result"
    description = "分析回测结果，解读关键指标并给出优化建议。支持通过回测ID从数据库读取，或直接传入结果数据。"
    parameters = {
        "type": "object",
        "properties": {
            "backtest_id": {"type": "string", "description": "回测任务ID，从数据库读取结果"},
            "result_file": {"type": "string", "description": "回测结果JSON文件路径"},
            "result_data": {"type": "string", "description": "直接传入的回测结果JSON字符串"},
        },
        "required": [],
    }

    param_template = {}

    async def execute(
        self,
        backtest_id: str | None = None,
        result_file: str | None = None,
        result_data: str | None = None,
        **kwargs: Any,
    ) -> str:
        from cli.strategy import analyze_backtest_result
        return analyze_backtest_result(backtest_id, result_file, result_data)


class OptimizeStrategyParamsTool(Tool):
    """优化策略参数"""

    name = "optimize_strategy_params"
    description = "通过网格搜索自动寻找最优策略参数。遍历参数组合并按目标指标排序。"
    parameters = {
        "type": "object",
        "properties": {
            "strategy_name": {"type": "string", "description": "策略名称"},
            "param_ranges": {"type": "string", "description": "参数搜索范围，JSON格式，如'{\"fast_period\": [5,10,15,20], \"slow_period\": [20,30,40,50]}'"},
            "symbols": {"type": "string", "description": "交易对列表，逗号分隔，如'BTCUSDT,ETHUSDT'"},
            "timeframe": {"type": "string", "description": "时间周期，如'1h', '4h', '1d'", "default": "1h"},
            "metric": {"type": "string", "description": "优化目标指标", "default": "sharpe_ratio"},
            "max_iterations": {"type": "integer", "description": "最大迭代次数", "default": 50},
        },
        "required": ["strategy_name", "param_ranges"],
    }

    param_template = {}

    async def execute(
        self,
        strategy_name: str,
        param_ranges: str,
        symbols: str = "BTCUSDT",
        timeframe: str = "1h",
        metric: str = "sharpe_ratio",
        max_iterations: int = 50,
        **kwargs: Any,
    ) -> str:
        from cli.strategy import optimize_strategy_params
        return optimize_strategy_params(strategy_name, param_ranges, symbols, timeframe, metric, max_iterations)


class DiagnoseStrategyTool(Tool):
    """诊断策略"""

    name = "diagnose_strategy"
    description = "诊断策略问题，分析策略亏损原因。通过静态分析代码和回测数据找出常见问题。"
    parameters = {
        "type": "object",
        "properties": {
            "strategy_name": {"type": "string", "description": "策略名称"},
            "backtest_id": {"type": "string", "description": "回测任务ID（可选），用于分析实际交易数据"},
        },
        "required": ["strategy_name"],
    }

    param_template = {}

    async def execute(
        self,
        strategy_name: str,
        backtest_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        from cli.strategy import diagnose_strategy
        return diagnose_strategy(strategy_name, backtest_id)


class DeployStrategyTool(Tool):
    """部署策略"""

    name = "deploy_strategy"
    description = "将策略部署到Worker实盘运行。创建Worker记录并可选择自动启动。"
    parameters = {
        "type": "object",
        "properties": {
            "strategy_name": {"type": "string", "description": "策略名称"},
            "strategy_file_name": {"type": "string", "description": "策略文件名（不含.py后缀）"},
            "exchange": {"type": "string", "description": "交易所名称，如'binance'", "default": "binance"},
            "symbols": {"type": "string", "description": "交易对列表，逗号分隔，如'BTCUSDT,ETHUSDT'"},
            "timeframe": {"type": "string", "description": "时间周期，如'1h'", "default": "1h"},
            "initial_capital": {"type": "number", "description": "初始资金", "default": 100000},
            "trading_mode": {"type": "string", "description": "交易模式：demo(模拟)/live(实盘)", "default": "demo"},
            "auto_start": {"type": "boolean", "description": "是否自动启动", "default": False},
        },
        "required": ["strategy_name", "symbols"],
    }

    param_template = {}

    async def execute(
        self,
        strategy_name: str,
        symbols: str,
        strategy_file_name: str | None = None,
        exchange: str = "binance",
        timeframe: str = "1h",
        initial_capital: float = 100000,
        trading_mode: str = "demo",
        auto_start: bool = False,
        **kwargs: Any,
    ) -> str:
        from cli.strategy import deploy_strategy
        return deploy_strategy(
            strategy_name,
            symbols,
            strategy_file_name,
            exchange,
            timeframe,
            initial_capital,
            trading_mode,
            auto_start,
        )


TOOLS_MAP = {
    "run_backtest": RunBacktestTool,
    "generate_strategy": GenerateStrategyTool,
    "analyze_backtest_result": AnalyzeBacktestResultTool,
    "optimize_strategy_params": OptimizeStrategyParamsTool,
    "diagnose_strategy": DiagnoseStrategyTool,
    "deploy_strategy": DeployStrategyTool,
}
