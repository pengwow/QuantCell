#!/usr/bin/env python3
"""
测试向资产池添加资产
"""

from collector.db.models import DataPoolBusiness

def main():
    """测试向资产池添加资产"""
    try:
        result = DataPoolBusiness.add_assets(3, ["btcusdt", "ethusdt", "bnbusdt"], "crypto")
        print(f"向资产池添加资产结果: {result}")
        if result:
            print("测试成功!")
        else:
            print("测试失败!")
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
