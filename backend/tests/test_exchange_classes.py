# 测试只导入和实例化交易所类，不连接到API

def test_binance_import():
    """测试导入BinanceExchange类"""
    try:
        from exchange.binance.connector import BinanceExchange
        print("✓ 成功导入BinanceExchange类")
        return True
    except Exception as e:
        print(f"✗ 导入BinanceExchange类失败: {e}")
        return False

def test_okx_import():
    """测试导入OkxExchange类"""
    try:
        from exchange.okx.connector import OkxExchange
        print("✓ 成功导入OkxExchange类")
        return True
    except Exception as e:
        print(f"✗ 导入OkxExchange类失败: {e}")
        return False

def test_exchange_base_class():
    """测试导入Exchange基类"""
    try:
        from exchange import Exchange
        print("✓ 成功导入Exchange基类")
        return True
    except Exception as e:
        print(f"✗ 导入Exchange基类失败: {e}")
        return False

def test_exchange_factory_import():
    """测试导入ExchangeFactory类"""
    try:
        from exchange.exchange import ExchangeFactory
        print("✓ 成功导入ExchangeFactory类")
        return True
    except Exception as e:
        print(f"✗ 导入ExchangeFactory类失败: {e}")
        return False

if __name__ == "__main__":
    print("开始测试交易所类导入...\n")
    
    tests = [
        test_exchange_base_class,
        test_binance_import,
        test_okx_import,
        test_exchange_factory_import
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n测试完成: {passed}/{total} 测试通过")
    if passed == total:
        print("✓ 所有测试通过！")
    else:
        print("✗ 部分测试失败！")
