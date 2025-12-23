#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试加密货币数据下载API

该脚本用于测试 /api/data/download/crypto 接口，发送POST请求下载加密货币数据
"""

import json
import sys

import requests


def test_download_crypto():
    """测试加密货币数据下载API
    
    发送POST请求到 /api/data/download/crypto 接口，测试加密货币数据下载功能
    
    Returns:
        bool: 请求是否成功
    """
    # 定义API地址
    BASE_URL = "http://localhost:8000"
    DOWNLOAD_CRYPTO_URL = f"{BASE_URL}/api/data/download/crypto"
    
    # 定义请求参数
    data = {
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "interval": ["1d", "1h"],
        "start": "2023-01-01",
        "end": "2023-01-02",
        "exchange": "binance",
        "max_workers": 2,
        "candle_type": "spot"
    }
    
    print("正在发送请求到加密货币数据下载API...")
    print(f"请求URL: {DOWNLOAD_CRYPTO_URL}")
    print(f"请求参数: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    try:
        # 发送POST请求
        response = requests.post(DOWNLOAD_CRYPTO_URL, json=data, timeout=30)
        
        print(f"\n响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        
        if response.status_code == 200:
            print("\n✅ 请求成功！加密货币数据下载API测试通过")
            return True
        else:
            print(f"\n❌ 请求失败，状态码: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 连接失败，请确保FastAPI服务正在{BASE_URL}运行")
        return False
    except requests.exceptions.Timeout:
        print("\n❌ 请求超时")
        return False
    except Exception as e:
        print(f"\n❌ 请求发生异常: {str(e)}")
        return False


if __name__ == "__main__":
    """主函数，执行测试并返回结果"""
    success = test_download_crypto()
    sys.exit(0 if success else 1)
