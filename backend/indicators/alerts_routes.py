"""指标信号提醒路由：规则 CRUD + 手动测试发送（P2-07）。

路由只做参数校验与会话编排，评估逻辑在 indicators/alerts.py；
通知投递复用 common/notifications 统一服务（websocket/email/feishu/wecom）。
"""

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from common.notifications.models import (
    NotificationCategory,
    NotificationChannel,
    NotificationLevel,
)
from common.notifications.service import notification_service
from common.schemas import ApiResponse
from indicators import alerts
from indicators.executor import IndicatorExecutor
from indicators.models import CustomIndicator, CustomIndicatorBusiness, IndicatorAlertRule
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger
from utils.rbac import is_guest_user

logger = get_logger(__name__, LogType.APPLICATION)

router = APIRouter(prefix="/api/v1/indicators/alerts", tags=["指标信号提醒"])


class AlertRuleUpsert(BaseModel):
    """创建提醒规则的请求体。"""

    indicator_id: int = Field(description="指标 ID")
    name: str = Field(default="", max_length=100, description="规则名称")
    symbol: str = Field(min_length=1, max_length=50, description="标的，如 BTCUSDT")
    period: str = Field(min_length=1, max_length=20, description="K线周期，如 1h")
    market_type: str = Field(default="crypto", pattern="^(stock|futures|crypto)$", description="市场类型")
    crypto_type: str = Field(default="spot", pattern="^(spot|future)$", description="加密货币类型")
    params: dict[str, Any] = Field(default_factory=dict, description="指标参数")
    plot_name: str = Field(default="", max_length=100, description="监控的 plot 线名，空=第一个")
    op: str = Field(default="gt", pattern="^(gt|lt|cross_up|cross_down)$", description="条件类型")
    threshold: float = Field(default=0.0, description="阈值")
    channels: list[str] = Field(default_factory=lambda: ["websocket"], description="通知渠道")
    frequency: int = Field(default=30, ge=1, le=1440, description="触发去重窗口（分钟）")
    enabled: bool = Field(default=True, description="是否启用")


class AlertRuleUpdate(BaseModel):
    """更新提醒规则：全字段可选，仅更新显式传入的字段。"""

    name: str | None = Field(default=None, max_length=100)
    symbol: str | None = Field(default=None, min_length=1, max_length=50)
    period: str | None = Field(default=None, min_length=1, max_length=20)
    market_type: str | None = Field(default=None, pattern="^(stock|futures|crypto)$")
    crypto_type: str | None = Field(default=None, pattern="^(spot|future)$")
    params: dict[str, Any] | None = None
    plot_name: str | None = Field(default=None, max_length=100)
    op: str | None = Field(default=None, pattern="^(gt|lt|cross_up|cross_down)$")
    threshold: float | None = None
    channels: list[str] | None = None
    frequency: int | None = Field(default=None, ge=1, le=1440)
    enabled: bool | None = None


def validate_channels(channels: list[str]) -> list[NotificationChannel]:
    """渠道名转枚举，非法值统一 400。"""
    try:
        return [NotificationChannel(c) for c in channels]
    except ValueError as e:
        valid = [c.value for c in NotificationChannel]
        raise HTTPException(status_code=400, detail=f"无效通知渠道: {e}，可选值: {valid}") from e


def _rule_to_dict(row: IndicatorAlertRule) -> dict[str, Any]:
    """ORM 行转 API dict（JSON 文本字段解包）。"""
    return {
        "id": row.id,
        "indicator_id": row.indicator_id,
        "name": row.name or "",
        "symbol": row.symbol,
        "period": row.period,
        "market_type": row.market_type,
        "crypto_type": row.crypto_type,
        "params": json.loads(row.params) if row.params else {},
        "plot_name": row.plot_name or "",
        "op": row.op,
        "threshold": float(row.threshold) if row.threshold is not None else 0.0,
        "channels": json.loads(row.channels) if row.channels else [],
        "frequency": row.frequency,
        "enabled": bool(row.enabled),
        "last_fired_at": row.last_fired_at.isoformat() + "Z" if row.last_fired_at else None,
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
    }


def _get_rule_row_or_404(db, rule_id: int) -> IndicatorAlertRule:
    row = db.get(IndicatorAlertRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"提醒规则不存在: {rule_id}")
    return row


def _assert_indicator_exists(indicator_id: int) -> None:
    with get_db_session() as db:
        if db.get(CustomIndicator, indicator_id) is None:
            raise HTTPException(status_code=404, detail=f"指标不存在: {indicator_id}")


@router.get("", summary="提醒规则列表", description="按 indicator_id 过滤（可选），返回全部指标信号提醒规则。")
async def list_alert_rules(indicator_id: int | None = None):
    with get_db_session() as db:
        stmt = select(IndicatorAlertRule).order_by(IndicatorAlertRule.id.desc())
        if indicator_id is not None:
            stmt = stmt.where(IndicatorAlertRule.indicator_id == indicator_id)
        rows = db.scalars(stmt).all()
        return ApiResponse(code=0, message="ok", data=[_rule_to_dict(r) for r in rows])


@router.post("", summary="创建提醒规则", description="为指定指标创建信号提醒规则，校验指标存在性与通知渠道合法性。")
async def create_alert_rule(request_body: AlertRuleUpsert, http_request: Request):
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权创建提醒规则")
    validate_channels(request_body.channels)
    _assert_indicator_exists(request_body.indicator_id)
    with get_db_session() as db:
        row = IndicatorAlertRule(
            indicator_id=request_body.indicator_id,
            name=request_body.name,
            symbol=request_body.symbol.upper(),
            period=request_body.period,
            market_type=request_body.market_type,
            crypto_type=request_body.crypto_type,
            params=json.dumps(request_body.params, ensure_ascii=False),
            plot_name=request_body.plot_name,
            op=request_body.op,
            threshold=request_body.threshold,
            channels=json.dumps(request_body.channels),
            frequency=request_body.frequency,
            enabled=request_body.enabled,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(f"创建提醒规则: id={row.id} indicator_id={row.indicator_id} {row.symbol} {row.period} {row.op}")
        return ApiResponse(code=0, message="已创建", data=_rule_to_dict(row))


@router.put("/{rule_id}", summary="更新提醒规则", description="更新规则字段；enabled=false 即暂停提醒。")
async def update_alert_rule(rule_id: int, request_body: AlertRuleUpdate, http_request: Request):
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权更新提醒规则")
    updates = request_body.model_dump(exclude_unset=True)
    if "channels" in updates:
        validate_channels(updates["channels"])
    with get_db_session() as db:
        row = _get_rule_row_or_404(db, rule_id)
        for field, value in updates.items():
            if field == "params":
                row.params = json.dumps(value, ensure_ascii=False)
            elif field == "channels":
                row.channels = json.dumps(value)
            elif field == "symbol":
                setattr(row, field, value.upper())
            else:
                setattr(row, field, value)
        db.commit()
        db.refresh(row)
        return ApiResponse(code=0, message="已更新", data=_rule_to_dict(row))


@router.delete("/{rule_id}", summary="删除提醒规则")
async def delete_alert_rule(rule_id: int, http_request: Request):
    if is_guest_user(http_request):
        raise HTTPException(status_code=403, detail="访客无权删除提醒规则")
    with get_db_session() as db:
        row = _get_rule_row_or_404(db, rule_id)
        db.delete(row)
        db.commit()
        logger.info(f"删除提醒规则: id={rule_id}")
        return ApiResponse(code=0, message="已删除", data={"id": rule_id})


@router.post(
    "/{rule_id}/test", summary="测试发送提醒", description="按当前数据评估一次并强制发送测试通知（不写入去重窗口）。"
)
async def test_alert_rule(rule_id: int):
    with get_db_session() as db:
        row = _get_rule_row_or_404(db, rule_id)
        rule = alerts._rule_snapshot(row)
    # 指标代码从 Business 侧取（与执行器同一读取口径）
    code = CustomIndicatorBusiness.get_code(rule["indicator_id"])
    if not code:
        raise HTTPException(status_code=404, detail=f"指标不存在或已删除: {rule['indicator_id']}")

    bars = alerts.fetch_kline_bars(rule)
    evaluation = await alerts.evaluate_rule(rule, code, IndicatorExecutor(timeout=10.0), bars)
    title, message = alerts.build_alert_texts(rule, evaluation)
    channels = validate_channels(rule["channels"])
    send_result = await notification_service.send_notification(
        title=f"[测试] {title}",
        content=message,
        level=NotificationLevel.WARNING,
        category=NotificationCategory.ALERT,
        channels=channels,
        metadata={"rule_id": rule_id, "triggered": bool(evaluation.get("triggered")), "test": True},
    )
    return ApiResponse(
        code=0,
        message="测试发送完成",
        data={"evaluation": evaluation, "send_result": send_result, "notified_at": datetime.now(UTC).isoformat()},
    )
