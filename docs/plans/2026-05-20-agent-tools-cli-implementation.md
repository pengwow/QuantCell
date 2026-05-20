# Agent工具CLI化实施计划

## 概述
基于设计文档 `2026-05-20-agent-tools-cli-design.md`，本计划详细说明实施步骤。

## 实施阶段

### 阶段一：创建 strategy_cli.py
**目标：** 将策略相关工具迁移到CLI

**任务清单：**
1. 创建 `backend/scripts/strategy_cli.py` 文件
2. 实现 `list_strategies()` 函数
   - 调用 `strategy.service.StrategyService.get_strategy_list()`
   - 格式化输出策略列表
3. 实现 `get_strategy_detail(strategy_id)` 函数
   - 查询数据库获取策略名称
   - 调用 `StrategyService.get_strategy_detail()`
   - 格式化输出策略详情
4. 实现 `generate_strategy(requirement, name, indicators)` 函数
   - 调用 `ai_model.strategy_generator.StrategyGenerator`
   - 调用 `ai_model.code_validator.CodeValidator`
   - 保存生成的策略文件
5. 实现 `analyze_backtest_result(backtest_id, result_file, result_data)` 函数
   - 调用 `backtest.result_analysis.ResultAnalyzer`
   - 生成优化建议
6. 实现 `optimize_strategy_params(strategy_name, param_ranges, symbols, timeframe, metric)` 函数
   - 调用 `backtest.service.BacktestService`
   - 执行网格搜索
7. 实现 `diagnose_strategy(strategy_name, backtest_id)` 函数
   - 静态分析策略代码
   - 分析回测数据
8. 实现 `deploy_strategy(strategy_name, symbols, exchange, timeframe, auto_start)` 函数
   - 调用 `worker.core_service.WorkerCoreService`
   - 创建Worker记录
9. 重构 `agent/tools/trading/strategy.py`
   - 将每个工具的 `execute` 方法改为调用CLI函数
10. 编写测试
    - 测试每个CLI函数的正常流程
    - 测试异常处理

**验收标准：**
- [ ] strategy_cli.py 中所有函数可独立运行
- [ ] agent工具正常工作，调用CLI函数
- [ ] 所有测试通过

---

### 阶段二：创建 market_cli.py
**目标：** 将市场数据工具迁移到CLI

**任务清单：**
1. 创建 `backend/scripts/market_cli.py` 文件
2. 实现 `get_klines(symbol, timeframe, limit, exchange)` 函数
   - 调用 `collector.services.market_data_service.MarketDataService`
   - 或调用 `collector.services.kline_factory.KlineDataFactory`
3. 实现 `get_ticker(symbol, exchange)` 函数
   - 调用ccxt库获取实时行情
4. 实现 `get_crypto_symbols(exchange, filter, limit, market_type)` 函数
   - 调用ccxt库获取交易对列表
5. 实现 `fetch_market_data(symbol, data_type, interval, limit, market_type)` 函数
   - 整合K线和行情获取
6. 重构 `agent/tools/trading/market_data.py`
   - 将每个工具的 `execute` 方法改为调用CLI函数
7. 编写测试

**验收标准：**
- [ ] market_cli.py 中所有函数可独立运行
- [ ] agent工具正常工作
- [ ] 所有测试通过

---

### 阶段三：创建 news_cli.py
**目标：** 将新闻工具迁移到CLI

**任务清单：**
1. 创建 `backend/scripts/news_cli.py` 文件
2. 实现 `get_news(query, category, count)` 函数
   - 调用NewsAPI获取新闻
   - 格式化输出
3. 实现 `get_market_sentiment()` 函数
   - 调用恐惧贪婪指数API
   - 格式化输出
4. 重构 `agent/tools/trading/news.py`
   - 将每个工具的 `execute` 方法改为调用CLI函数
5. 编写测试

**验收标准：**
- [ ] news_cli.py 中所有函数可独立运行
- [ ] agent工具正常工作
- [ ] 所有测试通过

---

### 阶段四：创建 web_cli.py
**目标：** 将Web工具迁移到CLI

**任务清单：**
1. 创建 `backend/scripts/web_cli.py` 文件
2. 实现 `web_search(query, count, proxy)` 函数
   - 调用Brave Search API
   - 格式化搜索结果
3. 实现 `web_fetch(url, extract_mode, max_chars, proxy)` 函数
   - 获取网页内容
   - 提取可读文本
4. 重构 `agent/tools/web.py`
   - 将每个工具的 `execute` 方法改为调用CLI函数
5. 编写测试

**验收标准：**
- [ ] web_cli.py 中所有函数可独立运行
- [ ] agent工具正常工作
- [ ] 所有测试通过

---

### 阶段五：集成测试与文档
**目标：** 确保所有组件正常工作

**任务清单：**
1. 运行所有单元测试
2. 运行集成测试
   - 测试agent工具完整流程
   - 测试CLI独立运行
3. 更新README文档
   - 添加CLI使用说明
   - 添加Agent工具说明
4. 提交代码

**验收标准：**
- [ ] 所有测试通过
- [ ] 文档完整
- [ ] 代码已提交

---

## 时间估算

| 阶段 | 预计时间 | 依赖 |
|------|----------|------|
| 阶段一 | 2-3天 | 无 |
| 阶段二 | 1-2天 | 无 |
| 阶段三 | 0.5-1天 | 无 |
| 阶段四 | 0.5-1天 | 无 |
| 阶段五 | 1天 | 阶段一至四 |

**总计：** 5-8天

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Service层接口不匹配 | 中 | 在CLI层做适配转换 |
| 循环导入 | 低 | 使用延迟导入 |
| 测试覆盖不足 | 中 | 优先编写测试 |
| 性能问题 | 低 | CLI层是薄封装，影响可忽略 |

## 优先级

**高优先级：**
- strategy_cli.py（策略管理是核心功能）

**中优先级：**
- market_cli.py（市场数据常用）
- web_cli.py（Web工具常用）

**低优先级：**
- news_cli.py（新闻工具使用较少）
