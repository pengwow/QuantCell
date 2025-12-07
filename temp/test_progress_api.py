#!/usr/bin/env python3
"""
测试优化后的任务状态接口的进度显示功能
"""

import sys
import time
import requests
import json
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# API基础URL
BASE_URL = "http://localhost:8000"
DOWNLOAD_API = f"{BASE_URL}/api/data/download/crypto"
TASK_API = f"{BASE_URL}/api/data/task"

# 测试数据
test_data = {
    "exchange": "binance",
    "start": "2025-11-01",
    "end": "2025-11-03",  # 只下载3天数据，便于测试
    "interval": ["1h"],
    "max_workers": 1,
    "candle_type": "spot",
    "symbols": ["BTCUSDT"]  # 只下载BTCUSDT，便于测试
}

def test_progress_display():
    """测试优化后的进度显示功能"""
    logger.info("开始测试优化后的进度显示功能")
    
    try:
        # 发送POST请求，创建下载任务
        logger.info(f"发送POST请求到 {DOWNLOAD_API}")
        logger.info(f"请求参数: {json.dumps(test_data, indent=2)}")
        
        response = requests.post(DOWNLOAD_API, json=test_data)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"创建任务响应: {json.dumps(result, indent=2)}")
        
        if result.get("code") != 0:
            logger.error(f"创建任务失败: {result.get('message')}")
            return False
        
        # 获取任务ID
        task_id = result.get("data", {}).get("task_id")
        if not task_id:
            logger.error("未从响应中获取到task_id")
            return False
        
        logger.info(f"成功创建任务，任务ID: {task_id}")
        
        # 轮询任务状态，验证进度显示
        task_url = f"{TASK_API}/{task_id}"
        max_retries = 30  # 最多轮询30次
        retry_interval = 2  # 每2秒轮询一次
        
        for i in range(max_retries):
            logger.info(f"第 {i+1}/{max_retries} 次轮询任务状态: {task_url}")
            
            response = requests.get(task_url)
            response.raise_for_status()
            
            task_status = response.json()
            logger.info(f"任务状态响应: {json.dumps(task_status, indent=2)}")
            
            if task_status.get("code") != 0:
                logger.error(f"获取任务状态失败: {task_status.get('message')}")
                continue
            
            # 验证进度信息
            task_data = task_status.get("data", {})
            progress = task_data.get("progress", {})
            
            logger.info(f"当前进度: {progress.get('percentage', 0)}%")
            logger.info(f"当前状态: {progress.get('status')}")
            logger.info(f"当前处理: {progress.get('current')}")
            logger.info(f"完成数: {progress.get('completed')}/{progress.get('total')}")
            
            # 检查进度信息是否包含详细的状态描述
            if "status" in progress:
                logger.info("✅ 进度信息包含status字段")
            else:
                logger.error("❌ 进度信息不包含status字段")
                return False
            
            # 如果任务已完成或失败，退出轮询
            if task_data.get("status") in ["completed", "failed"]:
                logger.info(f"任务已{task_data.get('status')}，结束轮询")
                break
            
            # 等待一段时间后继续轮询
            time.sleep(retry_interval)
        
        logger.info("测试完成")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API请求失败: {e}")
        return False
    except Exception as e:
        logger.error(f"测试失败: {e}")
        logger.exception(e)
        return False

if __name__ == "__main__":
    success = test_progress_display()
    if success:
        logger.info("✅ 所有测试通过")
        sys.exit(0)
    else:
        logger.error("❌ 测试失败")
        sys.exit(1)