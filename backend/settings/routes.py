"""
系统设置模块API路由

提供系统配置管理和系统信息查询的RESTful API端点。

路由前缀:
    - /api/config: 配置管理
    - /api/system: 系统信息

标签: config-management, system-info

包含端点:
    - GET /api/config/: 获取所有配置
    - GET /api/config/{key}: 获取指定配置
    - PUT /api/config/{key}: 更新配置
    - POST /api/config/batch: 批量更新配置
    - GET /api/system/info: 获取系统信息
    - GET /api/system/health: 健康检查

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import os
import sys
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Body, HTTPException, Path, Request
from utils.logger import get_logger, LogType
from utils.rbac import is_guest_user

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# 导入JWT认证装饰器
from utils.auth import jwt_auth_required_sync
from utils.jwt_utils import create_jwt_token, generate_tokens, generate_guest_tokens


def hash_password(password: str) -> str:
    """对密码进行单向加密（SHA256）
    
    Args:
        password: 原始密码
        
    Returns:
        str: 加密后的密码哈希值
    """
    if not password:
        return ""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(password: str, hashed_password: str) -> bool:
    """验证密码是否与存储的哈希值匹配
    
    Args:
        password: 原始密码
        hashed_password: 存储的密码哈希值
        
    Returns:
        bool: 密码是否匹配
    """
    if not password or not hashed_password:
        return False
    return hash_password(password) == hashed_password

# 导入配置管理相关模块
from settings.models import SystemConfigBusiness as SystemConfig
from collector.db.models import UserBusiness
from settings.services import SystemService

# 导入统一的ApiResponse模型
from common.schemas import ApiResponse

# 导入详细的Schema模型
from settings.schemas import (
    ConfigBatchUpdateRequest,
    ConfigUpdateRequest,
    SystemConfigItem,
    SystemConfigSimple,
    SystemInfo
)

# 创建API路由实例
router = APIRouter()

# 创建认证API路由子路由（不需要前缀，单独处理）
auth_router = APIRouter(tags=["auth"])

# 创建配置管理API路由子路由
config_router = APIRouter(prefix="/api/config", tags=["config-management"])

# 创建系统信息API路由子路由
system_router = APIRouter(prefix="/api/system", tags=["system-info"])


@auth_router.post("/api/auth/login", response_model=ApiResponse)
def login(request: Request, credentials: Dict[str, str] = Body(...)):
    """用户登录

    仅支持注册用户登录，不再支持访客模式。

    Args:
        request: FastAPI请求对象
        credentials: 登录凭据，包含username和password

    Returns:
        ApiResponse: 包含JWT token的响应
    """
    try:
        username = credentials.get("username", "").strip()
        password = credentials.get("password", "").strip()

        if not username or not password:
            return ApiResponse(
                code=400,
                message="请输入用户名和密码",
                data=None
            )

        logger.info(f"用户登录尝试: {username}")

        user_info = UserBusiness.authenticate(username, password)
        if not user_info:
            logger.warning(f"用户登录失败: {username}")
            return ApiResponse(
                code=401,
                message="用户名或密码错误",
                data=None
            )

        tokens = generate_tokens(
            str(user_info["id"]),
            user_info.get("nickname") or username,
            role="user"
        )

        logger.info(f"用户登录成功: {username} (id={user_info['id']})")
        return ApiResponse(
            code=0,
            message="登录成功",
            data={
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "token_type": "Bearer",
                "user_id": user_info["id"],
                "username": username,
                "nickname": user_info.get("nickname"),
                "is_guest": False,
                "role": "user"
            }
        )
    except Exception as e:
        logger.error(f"登录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@auth_router.post("/api/auth/register", response_model=ApiResponse)
def register(request: Request, credentials: Dict[str, str] = Body(...)):
    """用户注册

    创建新用户账号，注册后可直接使用用户名密码登录。

    Args:
        request: FastAPI请求对象
        credentials: 注册信息，包含username、password（可选confirm_password）

    Returns:
        ApiResponse: 包含注册结果的响应
    """
    try:
        username = credentials.get("username", "").strip()
        password = credentials.get("password", "").strip()

        if not username:
            return ApiResponse(code=400, message="用户名不能为空", data=None)
        if len(username) < 2:
            return ApiResponse(code=400, message="用户名至少需要2个字符", data=None)
        if len(username) > 50:
            return ApiResponse(code=400, message="用户名不能超过50个字符", data=None)
        if not password:
            return ApiResponse(code=400, message="密码不能为空", data=None)
        if len(password) < 6:
            return ApiResponse(code=400, message="密码至少需要6个字符", data=None)

        logger.info(f"用户注册尝试: {username}")

        user_info = UserBusiness.create(username, password)
        if not user_info:
            logger.warning(f"用户注册失败，用户已存在: {username}")
            return ApiResponse(
                code=409,
                message="用户名已被注册",
                data=None
            )

        logger.info(f"用户注册成功: {username} (id={user_info['id']})")
        return ApiResponse(
            code=0,
            message="注册成功",
            data={
                "user_id": user_info["id"],
                "username": user_info["username"],
                "nickname": user_info["nickname"],
            }
        )
    except Exception as e:
        logger.error(f"注册失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@auth_router.post("/api/auth/logout", response_model=ApiResponse)
def logout(request: Request):
    """用户注销

    清除前端token即可完成注销。后端返回确认信息。
    前端需在调用此接口后清除本地存储的token并跳转到登录页。

    Args:
        request: FastAPI请求对象

    Returns:
        ApiResponse: 注销结果
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.split(" ")[1] if " " in auth_header else auth_header
        
        logger.info(f"用户注销请求: token={token[:20]}..." if token else "无token注销")

        return ApiResponse(
            code=0,
            message="注销成功",
            data=None
        )
    except Exception as e:
        logger.error(f"注销失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.get("/", response_model=ApiResponse)
def get_all_configs(request: Request):
    """获取所有系统配置

    按 name 字段分组返回配置，格式为：
    {
        "exchange": {"binance": "...", "okx": "..."},
        "notification_channel": {"email": "...", "wecom": "..."}
    }

    Returns:
        ApiResponse[Dict[str, Dict[str, str]]]: 按 name 分组的配置数据

    Responses:
        200: 成功获取所有配置
        500: 获取配置失败
    """
    try:
        logger.info("开始获取所有系统配置")
        from utils.rbac import get_current_user_id
        user_id = get_current_user_id(request)

        # 获取所有配置的详细信息
        configs = SystemConfig.get_all_with_details(user_id=user_id)

        # 按 name 字段分组构建配置数据
        grouped_configs: Dict[str, Dict[str, str]] = {}
        for key, config in configs.items():
            name = config.get("name") or "default"  # 如果没有 name，使用 "default"

            # 初始化该 name 的分组
            if name not in grouped_configs:
                grouped_configs[name] = {}

            # 如果是敏感配置，返回空字符串，否则返回实际值
            if config.get("is_sensitive", False):
                grouped_configs[name][key] = ""
            else:
                grouped_configs[name][key] = config["value"]

        logger.info(f"成功获取所有系统配置，共 {len(configs)} 项，分为 {len(grouped_configs)} 组")

        return ApiResponse(
            code=0,
            message="获取所有配置成功",
            data=grouped_configs
        )
    except Exception as e:
        logger.error(f"获取所有配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.get("/{key}", response_model=ApiResponse)
def get_config(key: str = Path(..., description="配置项的键名，用于唯一标识一个配置项")):
    """获取指定键的系统配置
    
    Args:
        key: 配置键名，用于唯一标识一个配置项
        
    Returns:
        ApiResponse[SystemConfigItem]: 包含指定配置详细信息的响应
        
    Responses:
        200: 成功获取配置
        404: 配置不存在
        500: 获取配置失败
    """
    try:
        logger.info(f"开始获取配置: {key}")
        
        # 获取配置
        config = SystemConfig.get_with_details(key)
        
        if config:
            # 如果是敏感配置，返回空字符串
            if config.get("is_sensitive", False):
                config["value"] = ""
            logger.info(f"成功获取配置: {key}")
            return ApiResponse(
                code=0,
                message="获取配置成功",
                data=config
            )
        else:
            logger.warning(f"配置不存在: {key}")
            return ApiResponse(
                code=1,
                message="配置不存在",
                data={"key": key}
            )
    except Exception as e:
        logger.error(f"获取配置失败: key={key}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.post("/", response_model=ApiResponse)
def update_config(request: Request, config: ConfigUpdateRequest):
    """更新或创建系统配置
    
    Args:
        request: FastAPI请求对象，用于访问应用实例
        config: 配置更新请求体，包含配置的详细信息
    
    Returns:
        ApiResponse[SystemConfigItem]: 包含更新结果的响应
        
    Responses:
        200: 成功更新配置
        400: 请求数据格式错误
        403: 访客用户无权限
        500: 更新配置失败

    权限控制: 访客用户无法更新系统配置
    """
    # 检查是否为未认证用户
    if is_guest_user(request):
        logger.warning(f"未认证用户尝试更新配置(key={config.key})，已拦截")
        return ApiResponse(
            code=401,
            message="请先登录",
            data={"detail": "请登录后再修改系统配置"},
            timestamp=datetime.now()
        )

    try:
        from utils.rbac import get_current_user_id
        user_id = get_current_user_id(request)

        # 从Pydantic模型中获取配置字段
        key = config.key
        value = config.value
        description = config.description or ""
        plugin = config.plugin
        name = config.name
        is_sensitive = config.is_sensitive
        
        logger.info(f"开始更新配置: key={key}, value={value}, plugin={plugin}, name={name}, is_sensitive={is_sensitive}, user_id={user_id}")
        
        # 更新配置（绑定用户ID）
        success = SystemConfig.set(key, value, description, plugin, name, is_sensitive, user_id=user_id)
        
        if success:
            logger.info(f"成功更新配置: key={key}")
            # 刷新应用上下文配置
            from utils.config_manager import load_system_configs
            request.app.state.configs = load_system_configs()
            logger.info("系统配置上下文已刷新")

            # 如果是敏感配置，返回空字符串
            response_value = "" if is_sensitive else value

            return ApiResponse(
                code=0,
                message="更新配置成功",
                data={
                    "key": key,
                    "value": response_value,
                    "description": description,
                    "plugin": plugin,
                    "name": name,
                    "is_sensitive": is_sensitive
                }
            )
        else:
            logger.error(f"更新配置失败: key={key}")
            raise HTTPException(status_code=500, detail="更新配置失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新配置失败: error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.delete("/{key}", response_model=ApiResponse)
@jwt_auth_required_sync
def delete_config(request: Request, key: str = Path(..., description="要删除的配置项键名")):
    """删除指定键的系统配置
    
    Args:
        request: FastAPI请求对象，用于访问应用实例
        key: 要删除的配置项键名
        
    Returns:
        ApiResponse: 包含删除结果的响应
        
    Responses:
        200: 成功删除配置
        500: 删除配置失败
    """
    try:
        from utils.rbac import get_current_user_id
        user_id = get_current_user_id(request)
        logger.info(f"开始删除配置: {key}, user_id={user_id}")
        
        # 删除配置（绑定用户ID）
        success = SystemConfig.delete(key, user_id=user_id)
        
        if success:
            logger.info(f"成功删除配置: {key}")
            # 刷新应用上下文配置
            from utils.config_manager import load_system_configs
            request.app.state.configs = load_system_configs()
            logger.info("系统配置上下文已刷新")
            
            return ApiResponse(
                code=0,
                message="删除配置成功",
                data={"key": key}
            )
        else:
            logger.error(f"删除配置失败: {key}")
            raise HTTPException(status_code=500, detail="删除配置失败")
    except Exception as e:
        logger.error(f"删除配置失败: key={key}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.post("/batch", response_model=ApiResponse)
def update_configs_batch(request: Request, configs: Union[Dict[str, str], List[Dict[str, Any]], ConfigBatchUpdateRequest] = Body(...)):
    """批量更新系统配置

    Args:
        request: FastAPI请求对象，用于访问应用实例
        configs: 批量更新请求体，可以是以下三种格式之一：
            1. 键值对字典
            2. 配置项对象列表
            3. 包含configs字段的ConfigBatchUpdateRequest对象

    Returns:
        ApiResponse: 包含更新结果的响应

    Responses:
        200: 成功批量更新配置
        400: 请求数据格式错误
        403: 访客用户无权限
        500: 批量更新配置失败

    权限控制: 访客用户无法批量更新系统配置

    Request Examples:
        1. 字典格式:
           {
               "config1": "value1",
               "config2": "value2"
           }
        2. 列表格式:
           [
               {
                   "key": "config1",
                   "value": "value1",
                   "description": "配置项1",
                   "plugin": None,
                   "name": "基础配置",
                   "is_sensitive": false
               }
           ]
        3. ConfigBatchUpdateRequest格式:
           {
               "configs": {
                   "config1": "value1",
                   "config2": "value2"
               }
           }
    """
    # 检查是否为未认证用户
    if is_guest_user(request):
        logger.warning("未认证用户尝试批量更新配置，已拦截")
        return ApiResponse(
            code=401,
            message="请先登录",
            data={"detail": "请登录后再修改系统配置"},
            timestamp=datetime.now()
        )

    try:
        from utils.rbac import get_current_user_id
        user_id = get_current_user_id(request)
        logger.info(f"开始批量更新系统配置, user_id={user_id}")
        updated_count = 0
        batch_configs = configs
        
        # 处理不同格式的请求体
        if isinstance(batch_configs, ConfigBatchUpdateRequest):
            batch_configs = batch_configs.configs
        
        if isinstance(batch_configs, dict):
            for key, value in batch_configs.items():
                if not key.startswith("__v"):
                    logger.info(f"更新配置: key={key}, value={value}")
                    SystemConfig.set(key, value, user_id=user_id)
                    updated_count += 1
        elif isinstance(batch_configs, list):
            # 遍历配置项对象列表，逐个更新
            for config_item in batch_configs:
                key = config_item["key"]
                value = config_item["value"]
                description = config_item.get("description", "")
                plugin = config_item.get("plugin", None)
                name = config_item.get("name", None)
                is_sensitive = config_item.get("is_sensitive", False)

                # 如果是用户密码配置，进行单向加密
                if key == 'user.password' and value:
                    value = hash_password(value)
                    is_sensitive = True
                    logger.info(f"用户密码已加密存储")

                logger.info(f"更新配置: key={key}, value={'******' if is_sensitive else value}, plugin={plugin}, name={name}, is_sensitive={is_sensitive}")
                SystemConfig.set(
                    key=key,
                    value=value,
                    description=description,
                    plugin=plugin,
                    name=name,
                    is_sensitive=is_sensitive,
                    user_id=user_id
                )
                updated_count += 1
        
        logger.info(f"批量更新的配置数量: {updated_count}")

        # 刷新应用上下文配置
        from utils.config_manager import load_system_configs
        request.app.state.configs = load_system_configs()
        logger.info("系统配置上下文已刷新")
        
        return ApiResponse(
            code=0,
            message="批量更新配置成功",
            data={"updated_count": updated_count}
        )
    except Exception as e:
        logger.error(f"批量更新配置失败: error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.get("/plugin/{plugin_name}", response_model=ApiResponse)
def get_plugin_config(plugin_name: str = Path(..., description="插件的名称，用于过滤插件相关的配置项")):
    """获取指定插件的所有配置

    Args:
        plugin_name: 插件的名称，用于过滤插件相关的配置项

    Returns:
        ApiResponse[Dict[str, str]]: 包含指定插件配置的响应，值为敏感配置时返回空字符串
        
    Responses:
        200: 成功获取插件配置
        500: 获取插件配置失败
    """
    try:
        logger.info(f"开始获取插件配置: {plugin_name}")
        
        # 获取所有配置的详细信息
        all_configs = SystemConfig.get_all_with_details()
        
        # 过滤出与指定插件相关的配置
        plugin_configs = {}
        for key, config in all_configs.items():
            if config.get("plugin") == plugin_name:
                # 如果是敏感配置，返回空字符串
                if config.get("is_sensitive", False):
                    plugin_configs[key] = ""
                else:
                    plugin_configs[key] = config["value"]
        
        logger.info(f"成功获取插件配置，共 {len(plugin_configs)} 项")
        
        return ApiResponse(
            code=0,
            message="获取插件配置成功",
            data=plugin_configs
        )
    except Exception as e:
        logger.error(f"获取插件配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@system_router.get("/info", response_model=ApiResponse)
def get_system_info():
    """获取系统信息

    Returns:
        ApiResponse[SystemInfo]: 包含系统信息的响应，包括版本信息、运行状态和资源使用情况

    Responses:
        200: 成功获取系统信息
        500: 获取系统信息失败
    """
    try:
        system_service = SystemService()
        result = system_service.get_system_info()

        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["system_info"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data=result["error"]
            )
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        return ApiResponse(
            code=1,
            message="获取系统信息失败",
            data=str(e)
        )


@system_router.get("/sync-status", response_model=ApiResponse)
async def get_sync_status():
    """获取货币对同步状态

    Returns:
        ApiResponse: 同步状态信息
    """
    from services.symbol_sync import symbol_sync_manager

    return {
        "code": 0,
        "message": "获取同步状态成功",
        "data": {
            "status": symbol_sync_manager.status.value,
            "is_syncing": symbol_sync_manager.is_syncing,
            "consecutive_failures": symbol_sync_manager.consecutive_failures,
            "last_sync_time": symbol_sync_manager.last_sync_time.isoformat() if symbol_sync_manager.last_sync_time else None,
            "has_symbols_data": symbol_sync_manager.check_symbols_exist()
        }
    }


@system_router.post("/sync-symbols", response_model=ApiResponse)
async def trigger_sync_symbols(exchange: str = "binance"):
    """手动触发货币对同步

    Args:
        exchange: 交易所名称，默认为binance

    Returns:
        ApiResponse: 同步结果
    """
    from services.symbol_sync import symbol_sync_manager

    result = await symbol_sync_manager.async_perform_sync(exchange=exchange)

    if result.get("success"):
        return {
            "code": 0,
            "message": "同步任务已启动",
            "data": result
        }
    else:
        return {
            "code": 500,
            "message": result.get("message", "同步失败"),
            "data": result
        }


@system_router.get("/health", response_model=ApiResponse)
async def health_check():
    """系统健康检查

    Returns:
        ApiResponse: 健康状态
    """
    from services.symbol_sync import symbol_sync_manager

    return {
        "code": 0,
        "message": "系统运行正常",
        "data": {
            "status": "healthy",
            "sync_status": symbol_sync_manager.status.value,
            "has_symbols_data": symbol_sync_manager.check_symbols_exist()
        }
    }


# 创建通知设置API路由子路由
notification_router = APIRouter(prefix="/api/notifications", tags=["notification-config"])


@notification_router.get("/channels", response_model=ApiResponse)
@jwt_auth_required_sync
def get_notification_channels(request: Request):
    """获取所有通知渠道配置

    从系统配置中获取所有通知渠道配置，每个渠道作为一条记录，name=notification_channel。

    Args:
        request: FastAPI请求对象

    Returns:
        ApiResponse: 包含通知渠道配置的响应

    Responses:
        200: 成功获取配置
        401: 未授权访问
        500: 获取配置失败
    """
    try:
        logger.info("获取通知渠道配置")
        import json

        # 定义所有支持的渠道 (key: 渠道ID, value: 渠道显示名称)
        channel_configs = {
            "email": {
                "id": "email",
                "name": "email",
                "displayName": "邮件通知",
                "enabled": False,
                "isDefault": True,
                "config": {
                    "smtpHost": "",
                    "smtpPort": 465,
                    "security": "ssl",
                    "ignoreSSL": False,
                    "username": "",
                    "password": "",
                    "senderEmail": "",
                    "senderName": "",
                    "recipientEmail": ""
                }
            },
            "wecom": {
                "id": "wecom",
                "name": "wecom",
                "displayName": "企业微信",
                "enabled": False,
                "isDefault": False,
                "config": {
                    "webhookUrl": "",
                    "useCustomFormat": False,
                    "messageFormat": '{"msgtype": "text", "text": {"content": "${NOTIFIER_SUBJECT}\\n\\n${NOTIFIER_MESSAGE}"}}'
                }
            },
            "feishu": {
                "id": "feishu",
                "name": "feishu",
                "displayName": "飞书",
                "enabled": False,
                "isDefault": False,
                "config": {
                    "webhookUrl": "",
                    "useCustomFormat": False,
                    "messageFormat": '{"msg_type": "text", "content": {"text": "${NOTIFIER_SUBJECT}\\n\\n${NOTIFIER_MESSAGE}"}}'
                }
            }
        }

        channels = []

        # 从系统配置读取每个渠道的配置 (key=渠道ID, name=notification_channel)
        for channel_id, default_config in channel_configs.items():
            config = SystemConfig.get_with_details(channel_id)
            if config and config.get("value"):
                try:
                    channel_config = json.loads(config["value"])
                    # 确保有id字段
                    if "id" not in channel_config:
                        channel_config["id"] = channel_id
                    if "name" not in channel_config:
                        channel_config["name"] = channel_id
                    channels.append(channel_config)
                except json.JSONDecodeError:
                    logger.warning(f"解析渠道配置失败: {channel_id}")
                    channels.append(default_config)
            else:
                # 使用默认配置
                channels.append(default_config)

        return ApiResponse(
            code=0,
            message="获取通知渠道配置成功",
            data={"channels": channels}
        )
    except Exception as e:
        logger.error(f"获取通知渠道配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@notification_router.post("/channels", response_model=ApiResponse)
@jwt_auth_required_sync
def save_notification_channels(request: Request, channels: List[Dict[str, Any]] = Body(...)):
    """保存通知渠道配置

    将每个通知渠道配置保存为一条系统配置记录，name=渠道名称，key=notification_channel。

    Args:
        request: FastAPI请求对象
        channels: 通知渠道配置列表

    Returns:
        ApiResponse: 包含保存结果的响应

    Responses:
        200: 保存成功
        400: 请求数据格式错误
        401: 未授权访问
        500: 保存失败
    """
    try:
        logger.info("保存通知渠道配置")
        import json

        success_count = 0
        for channel in channels:
            # 优先使用key字段，如果没有则使用id字段
            channel_id = channel.get("key") or channel.get("id")
            if not channel_id:
                logger.warning("跳过没有key或id的渠道配置")
                continue

            # 将渠道配置序列化为JSON
            channel_config = {
                "id": channel_id,
                "name": channel_id,
                "enabled": channel.get("enabled", False),
                "isDefault": channel.get("isDefault", False),
                "config": channel.get("config", {})
            }
            config_json = json.dumps(channel_config, ensure_ascii=False)

            # 保存到系统配置，key=渠道ID，name=notification_channel
            success = SystemConfig.set(
                key=channel_id,
                value=config_json,
                description=f"{channel_id}通知配置",
                name="notification_channel"
            )

            if success:
                success_count += 1
                logger.info(f"保存渠道配置成功: {channel_id}")
            else:
                logger.error(f"保存渠道配置失败: {channel_id}")

        if success_count == len(channels):
            # 刷新应用上下文配置
            request.app.state.configs = load_system_configs()
            logger.info("所有通知渠道配置保存成功")
            return ApiResponse(
                code=0,
                message="保存通知渠道配置成功",
                data={"channels": channels}
            )
        else:
            logger.warning(f"部分渠道配置保存失败: {success_count}/{len(channels)}")
            return ApiResponse(
                code=0,
                message=f"部分配置保存成功 ({success_count}/{len(channels)})",
                data={"channels": channels}
            )
    except Exception as e:
        logger.error(f"保存通知渠道配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@notification_router.post("/test", response_model=ApiResponse)
@jwt_auth_required_sync
def test_notification(request: Request, test_request: Dict[str, Any] = Body(...)):
    """测试通知渠道

    发送测试消息到指定的通知渠道。

    Args:
        request: FastAPI请求对象
        test_request: 测试请求，包含channel_id和配置信息

    Returns:
        ApiResponse: 包含测试结果的响应

    Responses:
        200: 测试完成
        400: 请求数据格式错误
        401: 未授权访问
        500: 测试失败
    """
    import asyncio
    from common.notifications import notification_service, NotificationChannel

    try:
        channel_id = test_request.get("channel_id")
        config = test_request.get("config", {})

        logger.info(f"测试通知渠道: {channel_id}")

        if not channel_id:
            return ApiResponse(
                code=400,
                message="缺少channel_id参数",
                data=None
            )

        # 将channel_id转换为NotificationChannel枚举
        channel_map = {
            "email": NotificationChannel.EMAIL,
            "wecom": NotificationChannel.WECOM,
            "feishu": NotificationChannel.FEISHU,
            "websocket": NotificationChannel.WEBSOCKET,
        }

        channel_type = channel_map.get(channel_id)
        if not channel_type:
            return ApiResponse(
                code=400,
                message=f"未知的通知渠道: {channel_id}",
                data=None
            )

        # 异步执行通知测试
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            notification_service.test_channel(channel_type, config if config else None)
        )

        if result.get("success"):
            return ApiResponse(
                code=0,
                message=f"测试消息已成功发送到 {channel_id}",
                data={"channel_id": channel_id, "result": result}
            )
        else:
            return ApiResponse(
                code=500,
                message=f"测试发送失败: {result.get('error', '未知错误')}",
                data={"channel_id": channel_id, "error": result.get("error")}
            )

    except Exception as e:
        logger.error(f"测试通知渠道失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 创建交易所配置API路由子路由
exchange_router = APIRouter(prefix="/api/exchange-configs", tags=["exchange-config"])


@exchange_router.get("/", response_model=ApiResponse)
@jwt_auth_required_sync
def get_exchange_configs(request: Request):
    """获取所有交易所配置（扁平化存储）

    从扁平化存储中获取所有交易所配置，key格式为：exchange.{exchange_id}.{field}。

    Args:
        request: FastAPI请求对象

    Returns:
        ApiResponse: 包含交易所配置列表的响应
    """
    try:
        logger.info("获取交易所配置（扁平化存储）")

        from utils.rbac import get_current_user_id
        user_id = get_current_user_id(request)

        # 使用扁平化存储方法获取所有交易所配置
        exchanges_data = SystemConfig.get_all_flattened_by_prefix("exchange", user_id=user_id)
        exchange_configs = []

        for exchange_id, config_data in exchanges_data.items():
            exchange_configs.append({
                "id": exchange_id,
                "key": exchange_id,
                "name": config_data.get("name", exchange_id),
                "exchange_id": exchange_id,
                "trading_mode": config_data.get("trading_mode", "spot"),
                "quote_currency": config_data.get("quote_currency", "USDT"),
                "commission_rate": config_data.get("commission_rate", 0.001),
                "api_key": config_data.get("api_key", ""),
                "api_secret": config_data.get("api_secret", ""),
                "proxy_enabled": config_data.get("proxy_enabled", False),
                "proxy_url": config_data.get("proxy_url", ""),
                "proxy_username": config_data.get("proxy_username", ""),
                "proxy_password": config_data.get("proxy_password", ""),
                "is_enabled": config_data.get("is_enabled", False),
                "is_default": config_data.get("is_default", False),
            })

        return ApiResponse(
            code=0,
            message="获取交易所配置成功",
            data={"items": exchange_configs, "total": len(exchange_configs)}
        )
    except Exception as e:
        logger.error(f"获取交易所配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_router.post("/", response_model=ApiResponse)
@jwt_auth_required_sync
def create_exchange_config(request: Request, config: Dict[str, Any] = Body(...)):
    """创建交易所配置（扁平化存储）

    将交易所配置以扁平化方式保存，key格式为：exchange.{exchange_id}.{field}。

    Args:
        request: FastAPI请求对象
        config: 交易所配置数据

    Returns:
        ApiResponse: 包含创建结果的响应
    """
    try:
        logger.info(f"创建交易所配置（扁平化存储）: {config.get('exchange_id')}")

        exchange_id = config.get("exchange_id")
        if not exchange_id:
            return ApiResponse(code=400, message="交易所ID不能为空", data=None)

        # 构建配置字典
        config_data = {
            "name": config.get("name", exchange_id),
            "trading_mode": config.get("trading_mode", "spot"),
            "quote_currency": config.get("quote_currency", "USDT"),
            "commission_rate": config.get("commission_rate", 0.001),
            "api_key": config.get("api_key", ""),
            "api_secret": config.get("api_secret", ""),
            "proxy_enabled": config.get("proxy_enabled", False),
            "proxy_url": config.get("proxy_url", ""),
            "proxy_username": config.get("proxy_username", ""),
            "proxy_password": config.get("proxy_password", ""),
            "is_enabled": config.get("is_enabled", False),
            "is_default": config.get("is_default", False),
        }

        # 使用扁平化存储方法保存配置
        from utils.rbac import get_current_user_id
        user_id = get_current_user_id(request)
        prefix = f"exchange.{exchange_id}"
        success = SystemConfig.set_flattened(
            prefix=prefix,
            config_dict=config_data,
            name="exchange",
            description=f"{config.get('name', exchange_id)}交易所配置",
            user_id=user_id
        )

        if success:
            # 刷新应用上下文配置
            request.app.state.configs = load_system_configs()
            logger.info(f"交易所配置创建成功: {exchange_id}")
            return ApiResponse(
                code=0,
                message="交易所配置创建成功",
                data={"key": exchange_id, "exchange_id": exchange_id, **config_data}
            )
        else:
            logger.error(f"交易所配置创建失败: {exchange_id}")
            raise HTTPException(status_code=500, detail="创建配置失败")
    except Exception as e:
        logger.error(f"创建交易所配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_router.put("/{key}", response_model=ApiResponse)
@jwt_auth_required_sync
def update_exchange_config(request: Request, key: str, config: Dict[str, Any] = Body(...)):
    """更新交易所配置（扁平化存储）

    以扁平化方式更新交易所配置。

    Args:
        request: FastAPI请求对象
        key: 交易所英文名称
        config: 交易所配置数据

    Returns:
        ApiResponse: 包含更新结果的响应
    """
    try:
        logger.info(f"更新交易所配置（扁平化存储）: {key}")

        # 构建配置字典
        config_data = {
            "name": config.get("name", key),
            "trading_mode": config.get("trading_mode", "spot"),
            "quote_currency": config.get("quote_currency", "USDT"),
            "commission_rate": config.get("commission_rate", 0.001),
            "api_key": config.get("api_key", ""),
            "api_secret": config.get("api_secret", ""),
            "proxy_enabled": config.get("proxy_enabled", False),
            "proxy_url": config.get("proxy_url", ""),
            "proxy_username": config.get("proxy_username", ""),
            "proxy_password": config.get("proxy_password", ""),
            "is_enabled": config.get("is_enabled", False),
            "is_default": config.get("is_default", False),
        }

        # 使用扁平化存储方法更新配置
        from utils.rbac import get_current_user_id
        user_id = get_current_user_id(request)
        prefix = f"exchange.{key}"
        success = SystemConfig.set_flattened(
            prefix=prefix,
            config_dict=config_data,
            name="exchange",
            description=f"{config.get('name', key)}交易所配置",
            user_id=user_id
        )

        if success:
            # 刷新应用上下文配置
            request.app.state.configs = load_system_configs()
            logger.info(f"交易所配置更新成功: {key}")
            return ApiResponse(
                code=0,
                message="交易所配置更新成功",
                data={"key": key, "exchange_id": key, **config_data}
            )
        else:
            logger.error(f"交易所配置更新失败: {key}")
            raise HTTPException(status_code=500, detail="更新配置失败")
    except Exception as e:
        logger.error(f"更新交易所配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_router.delete("/{key}", response_model=ApiResponse)
@jwt_auth_required_sync
def delete_exchange_config(request: Request, key: str):
    """删除交易所配置（扁平化存储）

    删除指定交易所的所有扁平化配置记录。

    Args:
        request: FastAPI请求对象
        key: 交易所英文名称

    Returns:
        ApiResponse: 包含删除结果的响应
    """
    try:
        logger.info(f"删除交易所配置（扁平化存储）: {key}")

        # 使用扁平化存储方法删除配置
        from utils.rbac import get_current_user_id
        user_id = get_current_user_id(request)
        prefix = f"exchange.{key}"
        success = SystemConfig.delete_flattened(prefix, user_id=user_id)

        if success:
            # 刷新应用上下文配置
            request.app.state.configs = load_system_configs()
            logger.info(f"交易所配置删除成功: {key}")
            return ApiResponse(
                code=0,
                message="交易所配置删除成功",
                data={"key": key}
            )
        else:
            logger.error(f"交易所配置删除失败: {key}")
            raise HTTPException(status_code=500, detail="删除配置失败")
    except Exception as e:
        logger.error(f"删除交易所配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_router.get("/exchanges", response_model=ApiResponse)
@jwt_auth_required_sync
def get_supported_exchanges(request: Request):
    """获取支持的交易所列表

    Returns:
        ApiResponse: 包含支持的交易所列表
    """
    try:
        exchanges = [
            {"id": "binance", "name": "币安", "description": "全球最大的加密货币交易所"},
            {"id": "okx", "name": "OKX", "description": "全球领先的数字资产交易平台"},
            {"id": "bybit", "name": "Bybit", "description": "全球领先的加密货币衍生品交易所"},
            {"id": "gate", "name": "Gate.io", "description": "全球领先的数字资产交易平台"},
            {"id": "kucoin", "name": "KuCoin", "description": "全球知名的加密货币交易所"},
            {"id": "bitget", "name": "Bitget", "description": "全球领先的加密货币交易平台"},
        ]

        return ApiResponse(
            code=0,
            message="获取支持的交易所列表成功",
            data={"exchanges": exchanges}
        )
    except Exception as e:
        logger.error(f"获取支持的交易所列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册子路由
router.include_router(auth_router)
router.include_router(config_router)
router.include_router(system_router)
router.include_router(notification_router)
router.include_router(exchange_router)