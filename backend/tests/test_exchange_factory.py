from exchange.exchange import ExchangeFactory

# 测试ExchangeFactory的基本功能
def test_exchange_factory():
    """测试ExchangeFactory能否正确创建交易所实例"""
    try:
        # 测试创建binance交易所实例
        print("测试创建BinanceExchange实例...")
        binance_exchange = ExchangeFactory.create_exchange('binance')
        print(f"✓ 成功创建BinanceExchange实例: {binance_exchange}")
        
        # 测试创建okx交易所实例
        print("\n测试创建OkxExchange实例...")
        okx_exchange = ExchangeFactory.create_exchange('okx')
        print(f"✓ 成功创建OkxExchange实例: {okx_exchange}")
        
        print("\n✓ 所有测试通过!")
        return True
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_exchange_factory()
