# Agent工具CLI化设计文档

## 1. 概述

### 1.1 目标
将Agent模块的分析工具迁移到scripts目录的CLI模块，实现：
- 统一接口，便于测试调试
- 减少代码重复
- 支持独立使用
- 提高可维护性

### 1.2 核心原则
- CLI层是薄封装，直接调用Service层
- Agent工具层也是薄封装，调用CLI层
- 文件系统和Shell工具保留为agent工具
- Web工具创建独立的web_cli.py

## 2. 架构设计

### 2.1 分层架构
```
┌─────────────────────────────────────┐
│  Agent Tools (薄封装)               │  ← agent/tools/trading/*.py
├─────────────────────────────────────┤
│  CLI层 (薄封装)                     │  ← scripts/*_cli.py
├─────────────────────────────────────┤
│  Service层 (业务逻辑)               │  ← strategy/service.py, collector/services/*.py
├─────────────────────────────────────┤
│  Repository层 (数据访问)            │  ← collector/db/models.py
└─────────────────────────────────────┘
```

### 2.2 CLI模块结构
```
backend/scripts/
├── data_cli.py          # 数据管理（已有）
├── backtest_cli.py      # 回测管理（已有）
├── worker_cli.py        # Worker管理（已有）
├── agent_cli.py         # Agent管理（已有）
├── strategy_cli.py      # 策略管理（新建）
├── market_cli.py        # 市场数据（新建）
├── news_cli.py          # 新闻资讯（新建）
└── web_cli.py           # Web工具（新建）
```

## 3. 设计规范

### 3.1 CLI函数规范
```python
def function_name(param1: str, param2: int = None, db_session=None) -> str:
    """
    函数说明
    
    Args:
        param1: 参数1说明
        param2: 参数2说明
        db_session: 数据库会话（可选，不传则内部创建）
    
    Returns:
        str: 结果字符串或错误信息（以"错误:"开头）
    """
    try:
        # 调用service层
        from some.service import SomeService
        service = SomeService()
        result = service.some_method(param1, param2)
        
        # 格式化输出
        return format_result(result)
    except Exception as e:
        return f"错误: {e}"
```

### 3.2 Agent工具规范
```python
class SomeTool(Tool):
    name = "tool_name"
    description = "工具描述"
    parameters = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数描述"},
        },
        "required": ["param1"],
    }

    async def execute(self, param1: str, **kwargs) -> str:
        from scripts.some_cli import some_function
        return some_function(param1)
```

### 3.3 错误处理
- CLI函数返回错误字符串，以"错误:"开头
- 不抛出异常，所有异常在CLI内部捕获
- Agent工具直接返回CLI函数的结果

### 3.4 依赖注入
- CLI函数通过参数接收依赖（如db_session）
- 如果不传依赖，内部创建并管理生命周期
- 使用`try/finally`确保资源释放

## 4. 实施计划

### 4.1 第一阶段：创建 strategy_cli.py
**函数列表：**
- `list_strategies()` - 列出所有策略
- `get_strategy_detail(strategy_id)` - 获取策略详情
- `generate_strategy(requirement, name, indicators)` - 生成策略代码
- `analyze_backtest_result(backtest_id, result_file, result_data)` - 分析回测结果
- `optimize_strategy_params(strategy_name, param_ranges, symbols, timeframe, metric)` - 优化策略参数
- `diagnose_strategy(strategy_name, backtest_id)` - 诊断策略问题
- `deploy_strategy(strategy_name, symbols, exchange, timeframe, auto_start)` - 部署策略到Worker

**对应Service层：**
- `strategy.service.StrategyService`
- `backtest.service.BacktestService`
- `worker.core_service.WorkerCoreService`

### 4.2 第二阶段：创建 market_cli.py
**函数列表：**
- `get_klines(symbol, timeframe, limit, exchange)` - 获取K线数据
- `get_ticker(symbol, exchange)` - 获取最新行情
- `get_crypto_symbols(exchange, filter, limit, market_type)` - 获取交易对列表
- `fetch_market_data(symbol, data_type, interval, limit, market_type)` - 获取市场数据

**对应Service层：**
- `collector.services.market_data_service.MarketDataService`
- `collector.services.kline_factory.KlineDataFactory`

### 4.3 第三阶段：创建 news_cli.py
**函数列表：**
- `get_news(query, category, count)` - 获取财经新闻
- `get_market_sentiment()` - 获取市场情绪

**对应Service层：**
- 无现成Service，CLI层直接调用外部API

### 4.4 第四阶段：创建 web_cli.py
**函数列表：**
- `web_search(query, count, proxy)` - 网页搜索
- `web_fetch(url, extract_mode, max_chars, proxy)` - 获取网页内容

**对应Service层：**
- 无现成Service，CLI层直接调用httpx

### 4.5 第五阶段：重构Agent工具
**需要重构的工具：**
- `agent/tools/trading/strategy.py` - 调用strategy_cli.py
- `agent/tools/trading/market_data.py` - 调用market_cli.py
- `agent/tools/trading/news.py` - 调用news_cli.py
- `agent/tools/web.py` - 调用web_cli.py

**保留不变的工具：**
- `agent/tools/filesystem.py` - 文件系统工具
- `agent/tools/shell.py` - Shell命令工具

## 5. 示例代码

### 5.1 strategy_cli.py 示例
```python
"""策略管理CLI - 薄封装，调用Service层"""
from typing import Optional

def list_strategies(db_session=None) -> str:
    """列出所有策略"""
    try:
        from strategy.service import StrategyService
        service = StrategyService()
        strategies = service.get_strategy_list()
        
        if not strategies:
            return "系统中暂无策略"
        
        lines = ["可用策略列表:\n"]
        for s in strategies:
            lines.append(f"ID: {s.get('id')}, 名称: {s.get('name')}, 类型: {s.get('type', 'N/A')}")
        return "\n".join(lines)
    except Exception as e:
        return f"错误: {e}"


def get_strategy_detail(strategy_id: int, db_session=None) -> str:
    """获取策略详情"""
    try:
        from strategy.service import StrategyService
        from collector.db.database import SessionLocal, init_database_config
        from strategy.models import Strategy
        
        init_database_config()
        db = db_session or SessionLocal()
        try:
            strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if not strategy:
                return f"策略 ID {strategy_id} 不存在"
            
            service = StrategyService()
            detail = service.get_strategy_detail(strategy.name)
            if not detail:
                return f"获取策略详情失败"
            
            return (
                f"策略详情:\n"
                f"ID: {strategy.id}\n"
                f"名称: {detail.get('name')}\n"
                f"描述: {detail.get('description', 'N/A')}\n"
                f"版本: {detail.get('version', 'N/A')}\n"
                f"参数数量: {len(detail.get('params', []))}"
            )
        finally:
            if not db_session:
                db.close()
    except Exception as e:
        return f"错误: {e}"
```

### 5.2 Agent工具示例
```python
"""策略工具 - 薄封装，调用CLI层"""
from ..base import Tool

class ListStrategiesTool(Tool):
    name = "list_strategies"
    description = "列出系统中所有可用的交易策略。"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs) -> str:
        from scripts.strategy_cli import list_strategies
        return list_strategies()


class GetStrategyDetailTool(Tool):
    name = "get_strategy_detail"
    description = "获取指定策略的详细信息。"
    parameters = {
        "type": "object",
        "properties": {
            "strategy_id": {"type": "integer", "description": "策略 ID"},
        },
        "required": ["strategy_id"],
    }

    async def execute(self, strategy_id: int, **kwargs) -> str:
        from scripts.strategy_cli import get_strategy_detail
        return get_strategy_detail(strategy_id)
```

## 6. 测试策略

### 6.1 CLI测试
- 每个CLI函数独立测试
- 测试正常流程和异常流程
- 测试依赖注入（传入db_session）

### 6.2 Agent工具测试
- 测试工具参数验证
- 测试工具执行（mock CLI层）
- 集成测试（真实调用CLI层）

## 7. 迁移步骤

1. 创建新的CLI文件（strategy_cli.py, market_cli.py等）
2. 实现CLI函数，调用现有Service层
3. 编写CLI函数的单元测试
4. 重构Agent工具，改为调用CLI函数
5. 运行Agent工具的测试，确保功能正常
6. 更新文档

## 8. 风险与缓解

### 8.1 风险
- Service层接口不完全匹配CLI需求
- 循环导入问题
- 性能问题（多一层调用）

### 8.2 缓解措施
- 在CLI层做适配转换
- 使用延迟导入避免循环导入
- 性能影响可忽略（CLI层是薄封装）
