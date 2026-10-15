# Binance模块测试报告

## 现状

`tests/exchange/test_binance/` 目录下**仅保留** `test_integration.py`
（针对 `exchange.binance.BinanceClient` REST 客户端的集成测试）。

原先针对模拟盘交易的单元测试
（`test_paper_trading.py` / `test_edge_cases.py` / `test_performance.py` / `test_websocket.py`）
及其对应的业务模块已归档，相关测试与报告内容已从本文档移除。

## 运行测试

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend

# 集成测试（需要测试网 API 密钥，否则用例会被跳过）
export BINANCE_TESTNET_API_KEY="your_key"
export BINANCE_TESTNET_API_SECRET="your_secret"
python -m pytest tests/exchange/test_binance/ -v
```

> 未设置 `BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_API_SECRET` 时，
> 需要密钥的用例会标记为 skipped。

## 后续建议

1. **配置API密钥** - 设置环境变量以运行集成测试
2. **CI/CD集成** - 将测试集成到持续集成流程
