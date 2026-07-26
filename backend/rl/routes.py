# -*- coding: utf-8 -*-
"""RL 模块 API 路由

路由前缀: /api/rl
"""

import asyncio
import json
import time
from queue import Queue
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from utils.logger import get_logger, LogType
from common.schemas import ApiResponse

from .service import RLService

logger = get_logger(__name__, LogType.APPLICATION)

_rl_service: Optional[RLService] = None


def get_rl_service() -> RLService:
    global _rl_service
    if _rl_service is None:
        _rl_service = RLService()
    return _rl_service


router = APIRouter(prefix="/api/rl", tags=["rl"])


class RLTrainRequest(BaseModel):
    symbol: str = Field(..., description="交易对")
    algorithm: str = Field(default="ppo", description="算法")
    timesteps: int = Field(default=10_000, description="训练步数")
    learning_rate: float = Field(default=3e-4, description="学习率")
    reward: str = Field(default="pnl", description="奖励函数")
    initial_capital: float = Field(default=100_000, description="初始资金")
    transaction_cost: float = Field(default=0.001, description="交易费率")
    interval: str = Field(default="1h", description="K线周期")
    lookback_days: int = Field(default=90, description="回看天数")
    output_name: Optional[str] = Field(default=None, description="模型名称")
    
    # 前端兼容字段（data_source 格式: BTCUSDT_1h）
    data_source: Optional[str] = Field(default=None, description="数据源格式：symbol_interval")
    total_timesteps: Optional[int] = Field(default=None, description="训练步数（前端兼容）")
    reward_type: Optional[str] = Field(default=None, description="奖励函数（前端兼容）")
    
    def to_rl_config(self):
        """转换为 RLTrainConfig，处理前端兼容字段"""
        from .models import RLTrainConfig
        
        # 处理 data_source 拆分
        symbol = self.symbol
        interval = self.interval
        if self.data_source and not self.symbol:
            parts = self.data_source.split('_')
            if len(parts) >= 2:
                symbol = parts[0]
                interval = '_'.join(parts[1:])
        
        # 处理兼容字段优先级
        timesteps = self.timesteps
        if self.total_timesteps is not None:
            timesteps = self.total_timesteps
        
        reward = self.reward
        if self.reward_type:
            reward = self.reward_type
        
        return RLTrainConfig(
            symbol=symbol,
            algorithm=self.algorithm,
            timesteps=timesteps,
            learning_rate=self.learning_rate,
            reward=reward,
            initial_capital=self.initial_capital,
            transaction_cost=self.transaction_cost,
            interval=interval,
            lookback_days=self.lookback_days,
            output_name=self.output_name,
        )


@router.post("/train", response_model=ApiResponse)
def train_model(req: RLTrainRequest) -> ApiResponse:
    """启动 RL 训练"""
    try:
        config = req.to_rl_config()
        result = get_rl_service().train(config)
        return ApiResponse(code=0, message="训练完成", data=result)
    except Exception as e:
        logger.error(f"RL 训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/stream")
async def train_model_stream(req: RLTrainRequest):
    """流式训练 RL 模型（SSE 实时进度推送）

    返回 Server-Sent Events 格式的流式响应，实时推送训练进度：
    
    事件类型:
    - start: 训练开始
    - info: 信息（如数据加载完成）
    - progress: 训练进度（timestep, episode, episode_reward, mean_reward, elapsed_time）
    - complete: 训练完成（包含最终结果）
    - error: 错误信息
    """
    progress_queue: Queue = Queue()
    config = req.to_rl_config()

    async def event_generator():
        """SSE 事件生成器"""
        try:
            # 在后台线程中运行训练
            import threading
            
            def run_training():
                try:
                    result = get_rl_service().train_stream(config, progress_queue)
                    # 训练完成后推送结果
                    try:
                        progress_queue.put({
                            "type": "complete",
                            "result": result,
                            "timestamp": time.time(),
                        })
                    except Exception:
                        logger.error(f"推送训练完成结果失败，队列已满或出错")
                except Exception as e:
                    try:
                        progress_queue.put({
                            "type": "error",
                            "error": str(e),
                            "timestamp": time.time(),
                        })
                    except Exception:
                        logger.error(f"训练失败且无法发送错误消息: {e}")

            # 启动训练线程
            thread = threading.Thread(target=run_training, daemon=True)
            thread.start()

            # 循环读取队列并推送 SSE 事件
            while True:
                try:
                    # 非阻塞读取，避免线程阻塞
                    progress = progress_queue.get(timeout=1)
                    
                    event_type = progress.get("type", "progress")
                    event_data = json.dumps(progress, ensure_ascii=False)
                    
                    yield f"event: {event_type}\ndata: {event_data}\n\n"
                    
                    if event_type in ("complete", "error"):
                        break
                    
                    await asyncio.sleep(0)  # 让出控制权
                except Exception:
                    await asyncio.sleep(0.5)
                    continue

        except Exception as e:
            error_data = json.dumps({
                "type": "error",
                "error": str(e),
                "timestamp": time.time(),
            }, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/models", response_model=ApiResponse)
def list_models() -> ApiResponse:
    """列出已训练模型"""
    try:
        models = get_rl_service().list_models()
        return ApiResponse(code=0, message="success", data={"models": models})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/models/{model_name}", response_model=ApiResponse)
def delete_model(model_name: str) -> ApiResponse:
    """删除指定模型（包括模型文件和元数据）"""
    try:
        success = get_rl_service().delete_model(model_name)
        if success:
            return ApiResponse(code=0, message=f"模型 {model_name} 已删除")
        else:
            raise HTTPException(status_code=404, detail=f"模型 {model_name} 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模型失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RLBacktestRequest(BaseModel):
    model_path: str = Field(..., description="模型路径")
    symbol: str = Field(default="BTCUSDT", description="交易对")
    interval: str = Field(default="1h", description="K线周期")
    lookback_days: int = Field(default=90, description="回看天数")


@router.post("/backtest", response_model=ApiResponse)
def backtest_model(req: RLBacktestRequest) -> ApiResponse:
    """用训练好的模型回测"""
    try:
        result = get_rl_service().backtest(
            model_path=req.model_path,
            symbol=req.symbol,
            interval=req.interval,
            lookback_days=req.lookback_days,
        )
        return ApiResponse(code=0, message="回测完成", data=result)
    except Exception as e:
        logger.error(f"RL 回测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
