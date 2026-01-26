import json
from typing import Any, Dict, Optional

import sqlalchemy
from loguru import logger
from sqlalchemy import Boolean, Column, DateTime, Integer, Identity, String, Text, func, text
from sqlalchemy.orm import Session

from .database import Base

# SQLAlchemy模型定义

from datetime import datetime

class SystemConfig(Base):
    """系统配置SQLAlchemy模型
    
    对应system_config表的SQLAlchemy模型定义
    """
    __tablename__ = "system_config"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    name = Column(String, nullable=True, index=True)  # 配置名称，用于区分系统配置页面的子菜单名称
    plugin = Column(String, nullable=True, index=True)  # 插件名称，用于区分是插件配置还是基础配置
    is_sensitive = Column(Boolean, default=False)  # 是否敏感配置，敏感配置API不返回真实值
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class Task(Base):
    """任务SQLAlchemy模型
    
    对应tasks表的SQLAlchemy模型定义
    """
    __tablename__ = "tasks"
    
    task_id = Column(String, primary_key=True, index=True)
    task_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    total = Column(Integer, default=0)
    completed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    current = Column(String, default="")
    percentage = Column(Integer, default=0)
    params = Column(Text, default="{}")
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), index=True)


class Feature(Base):
    """特征信息SQLAlchemy模型
    
    对应features表的SQLAlchemy模型定义，用于存储特征信息
    """
    __tablename__ = "features"
    
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    feature_name = Column(String, nullable=False, index=True)
    freq = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class DataPool(Base):
    """资产池SQLAlchemy模型
    
    对应data_pools表的SQLAlchemy模型定义
    """
    __tablename__ = "data_pools"
    
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    type = Column(String, nullable=True, index=True)
    description = Column(Text, nullable=True)
    color = Column(String, nullable=True)
    tags = Column(Text, nullable=True)
    is_public = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # 添加联合唯一约束，确保同一类型下的资源池名称不重复
    __table_args__ = (
        sqlalchemy.UniqueConstraint('name', 'type', name='unique_name_type'),
    )


class DataPoolAsset(Base):
    """资产池资产关联SQLAlchemy模型
    
    对应data_pool_assets表的SQLAlchemy模型定义
    """
    __tablename__ = "data_pool_assets"
    
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)
    pool_id = Column(Integer, nullable=False, index=True)
    asset_id = Column(String, nullable=False, index=True)
    asset_type = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class CryptoSymbol(Base):
    """加密货币对SQLAlchemy模型
    
    对应crypto_symbols表的SQLAlchemy模型定义，用于存储加密货币对信息
    """
    __tablename__ = "crypto_symbols"
    
    # 使用Identity约束实现自增主键，兼容SQLite和DuckDB
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    base = Column(String, nullable=False, index=True)
    quote = Column(String, nullable=False, index=True)
    exchange = Column(String, nullable=False, index=True)
    active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False, index=True)  # 软删除标记
    precision = Column(Text, nullable=True)  # JSON字符串，存储精度信息
    limits = Column(Text, nullable=True)  # JSON字符串，存储限制信息
    type = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # 设置唯一约束，确保symbol + exchange的组合唯一
    __table_args__ = (
        sqlalchemy.UniqueConstraint('symbol', 'exchange', name='unique_symbol_exchange'),
    )


class CryptoSpotKline(Base):
    """加密货币现货K线数据SQLAlchemy模型
    
    对应crypto_spot_klines表的SQLAlchemy模型定义，用于存储加密货币现货K线数据
    """
    __tablename__ = "crypto_spot_klines"
    
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    interval = Column(String, nullable=False, index=True)
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(String, nullable=False)  # 使用字符串避免精度问题
    high = Column(String, nullable=False)  # 使用字符串避免精度问题
    low = Column(String, nullable=False)  # 使用字符串避免精度问题
    close = Column(String, nullable=False)  # 使用字符串避免精度问题
    volume = Column(String, nullable=False)  # 使用字符串避免精度问题
    unique_kline = Column(String, nullable=False, unique=True, index=True)  # 唯一标识符
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class CryptoFutureKline(Base):
    """加密货币合约K线数据SQLAlchemy模型
    
    对应crypto_future_klines表的SQLAlchemy模型定义，用于存储加密货币合约K线数据
    """
    __tablename__ = "crypto_future_klines"
    
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    interval = Column(String, nullable=False, index=True)
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(String, nullable=False)  # 使用字符串避免精度问题
    high = Column(String, nullable=False)  # 使用字符串避免精度问题
    low = Column(String, nullable=False)  # 使用字符串避免精度问题
    close = Column(String, nullable=False)  # 使用字符串避免精度问题
    volume = Column(String, nullable=False)  # 使用字符串避免精度问题
    unique_kline = Column(String, nullable=False, unique=True, index=True)  # 唯一标识符
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class StockKline(Base):
    """股票K线数据SQLAlchemy模型
    
    对应stock_klines表的SQLAlchemy模型定义，用于存储股票K线数据
    """
    __tablename__ = "stock_klines"
    
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    interval = Column(String, nullable=False, index=True)
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(String, nullable=False)  # 使用字符串避免精度问题
    high = Column(String, nullable=False)  # 使用字符串避免精度问题
    low = Column(String, nullable=False)  # 使用字符串避免精度问题
    close = Column(String, nullable=False)  # 使用字符串避免精度问题
    volume = Column(String, nullable=False)  # 使用字符串避免精度问题
    unique_kline = Column(String, nullable=False, unique=True, index=True)  # 唯一标识符
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class ScheduledTask(Base):
    """定时任务SQLAlchemy模型
    
    对应scheduled_tasks表的SQLAlchemy模型定义，用于存储定时任务配置
    """
    __tablename__ = "scheduled_tasks"
    
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    task_type = Column(String, nullable=False, default="download_crypto")
    status = Column(String, nullable=False, default="pending")  # pending, running, completed, failed, paused
    
    # 调度配置
    cron_expression = Column(String, nullable=True)  # CRON表达式
    interval = Column(String, nullable=True)  # 时间间隔，如1h, 1d, 1w
    start_time = Column(DateTime(timezone=True), nullable=True)  # 开始执行时间
    end_time = Column(DateTime(timezone=True), nullable=True)  # 结束执行时间
    frequency_type = Column(String, nullable=True)  # 频率类型：hourly, daily, weekly, monthly, cron
    
    # 数据采集配置
    symbols = Column(Text, nullable=True)  # JSON字符串，存储交易对列表
    exchange = Column(String, nullable=True)
    candle_type = Column(String, nullable=True, default="spot")
    save_dir = Column(String, nullable=True)
    max_workers = Column(Integer, nullable=True, default=1)
    
    # 执行状态
    last_run_time = Column(DateTime(timezone=True), nullable=True)  # 上次执行时间
    next_run_time = Column(DateTime(timezone=True), nullable=True)  # 下次执行时间
    last_result = Column(String, nullable=True)  # 上次执行结果
    error_message = Column(Text, nullable=True)  # 错误信息
    run_count = Column(Integer, default=0)  # 执行次数
    success_count = Column(Integer, default=0)  # 成功次数
    fail_count = Column(Integer, default=0)  # 失败次数
    
    # 增量采集配置
    incremental_enabled = Column(Boolean, default=True)  # 是否启用增量采集
    last_collected_date = Column(DateTime(timezone=True), nullable=True)  # 上次采集日期
    
    # 通知配置
    notification_enabled = Column(Boolean, default=False)  # 是否启用通知
    notification_type = Column(String, nullable=True)  # 通知类型：email, webhook
    notification_email = Column(String, nullable=True)  # 通知邮箱
    notification_webhook = Column(String, nullable=True)  # 通知Webhook
    
    # 元数据
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    created_by = Column(String, nullable=True, default="system")  # 创建者
    
    __table_args__ = (
        # 添加索引，提高查询性能
        sqlalchemy.Index('idx_scheduled_tasks_status', 'status'),
        sqlalchemy.Index('idx_scheduled_tasks_next_run_time', 'next_run_time'),
    )


class BacktestTask(Base):
    """回测任务SQLAlchemy模型
    
    对应backtest_tasks表的SQLAlchemy模型定义，用于存储回测任务信息
    """
    __tablename__ = "backtest_tasks"
    
    id = Column(String, primary_key=True, index=True)  # 任务唯一标识
    strategy_name = Column(String, nullable=False, index=True)  # 策略名称
    backtest_config = Column(Text, nullable=False)  # JSON格式，回测配置
    status = Column(String, nullable=False, default="pending", index=True)  # 任务状态: pending/running/completed/failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)  # 创建时间
    started_at = Column(DateTime(timezone=True), nullable=True)  # 开始执行时间
    completed_at = Column(DateTime(timezone=True), nullable=True)  # 完成时间
    result_id = Column(String, nullable=True)  # 关联的回测结果ID


class BacktestResult(Base):
    """回测结果SQLAlchemy模型
    
    对应backtest_results表的SQLAlchemy模型定义，用于存储回测结果信息
    """
    __tablename__ = "backtest_results"
    
    id = Column(String, primary_key=True, index=True)  # 结果唯一标识
    task_id = Column(String, nullable=False, index=True)  # 关联的回测任务ID
    strategy_name = Column(String, nullable=False, index=True)  # 策略名称
    symbol = Column(String, nullable=False, index=True)  # 货币对标识
    metrics = Column(Text, nullable=False)  # JSON格式，包含翻译后的指标
    trades = Column(Text, nullable=False)  # JSON格式，交易记录
    equity_curve = Column(Text, nullable=False)  # JSON格式，资金曲线
    strategy_data = Column(Text, nullable=False)  # JSON格式，策略数据
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)  # 创建时间
    
    # 添加外键约束
    __table_args__ = (
        sqlalchemy.ForeignKeyConstraint(['task_id'], ['backtest_tasks.id']),
    )


class Strategy(Base):
    """策略SQLAlchemy模型
    
    对应strategies表的SQLAlchemy模型定义，用于存储策略信息
    """
    __tablename__ = "strategies"
    
    id = Column(Integer, Identity(always=True), primary_key=True, index=True)  # 主键ID
    name = Column(String, unique=True, index=True)  # 策略名称，唯一
    filename = Column(String, nullable=False)  # 策略文件名
    content = Column(Text, nullable=True)  # 策略内容，存储策略的实际代码
    description = Column(Text, nullable=True)  # 策略描述
    parameters = Column(Text, nullable=True)  # JSON格式，策略参数定义
    version = Column(String, nullable=True, default="1.0.0")  # 策略版本
    tags = Column(Text, nullable=True)  # JSON格式，策略标签
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间


# 业务逻辑类

class SystemConfigBusiness:
    """系统配置模型类
    
    用于操作system_config表，提供CRUD操作方法
    兼容SQLite和DuckDB
    """
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """获取配置项的值
        
        Args:
            key: 配置项键名
            default: 默认值，如果配置项不存在则返回默认值
            
        Returns:
            Any: 配置项的值或默认值
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                return config.value
            return default
        except Exception as e:
            logger.error(f"获取配置失败: key={key}, error={e}")
            return default
        finally:
            db.close()
    
    @staticmethod
    def set(key: str, value: str, description: str = "", plugin: str = None, name: str = None, is_sensitive: bool = False) -> bool:
        """设置配置项的值
        
        Args:
            key: 配置项键名
            value: 配置项值
            description: 配置项描述
            plugin: 插件名称，用于区分是插件配置还是基础配置
            name: 配置名称，用于区分系统配置页面的子菜单名称
            is_sensitive: 是否为敏感配置，敏感配置API不返回真实值
            
        Returns:
            bool: 设置成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 检查配置是否已存在
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                # 更新现有配置
                config.value = value
                if description:
                    config.description = description
                if plugin is not None:
                    config.plugin = plugin
                if name is not None:
                    config.name = name
                config.is_sensitive = is_sensitive
            else:
                # 创建新配置
                config = SystemConfig(
                    key=key,
                    value=value,
                    description=description,
                    plugin=plugin,
                    name=name,
                    is_sensitive=is_sensitive
                )
                db.add(config)
            db.commit()
            logger.info(f"配置已更新: key={key}, value={value}, plugin={plugin}, name={name}, is_sensitive={is_sensitive}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新配置失败: key={key}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def delete(key: str) -> bool:
        """删除配置项
        
        Args:
            key: 配置项键名
            
        Returns:
            bool: 删除成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                db.delete(config)
                db.commit()
                logger.info(f"配置已删除: key={key}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除配置失败: key={key}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_all() -> Dict[str, str]:
        """获取所有配置项
        
        Returns:
            Dict[str, str]: 所有配置项，键为配置项键名，值为配置项值
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).all()
            return {config.key: config.value for config in configs}  # pyright: ignore[reportReturnType]
        except Exception as e:
            logger.error(f"获取所有配置失败: error={e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def get_with_details(key: str) -> Optional[Dict[str, Any]]:
        """获取配置项的详细信息
        
        Args:
            key: 配置项键名
            
        Returns:
            Optional[Dict[str, Any]]: 配置的详细信息，包括键、值、描述、插件、名称、是否敏感、创建时间和更新时间
        """
        from .database import SessionLocal, init_database_config
        import pytz
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                print(f"DEBUG: 原始created_at: {config.created_at}, type: {type(config.created_at)}")
                print(f"DEBUG: 原始updated_at: {config.updated_at}, type: {type(config.updated_at)}")
                
                def format_datetime(dt):
                    if dt is None:
                        return None
                    # 如果datetime对象没有时区信息，添加UTC时区
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.utc)
                        print(f"DEBUG: 添加时区后: {dt}")
                    # 转换为UTC+8时间并格式化为字符串
                    local_time = dt.astimezone(pytz.timezone('Asia/Shanghai'))
                    print(f"DEBUG: 转换为本地时间: {local_time}")
                    formatted = local_time.strftime('%Y-%m-%d %H:%M:%S')
                    print(f"DEBUG: 格式化后: {formatted}")
                    return formatted
                
                result = {
                    "key": config.key,
                    "value": config.value,
                    "description": config.description,
                    "plugin": config.plugin,
                    "name": config.name,
                    "is_sensitive": config.is_sensitive,
                    "created_at": format_datetime(config.created_at),
                    "updated_at": format_datetime(config.updated_at)
                }
                print(f"DEBUG: 返回结果: {result}")
                return result
            return None
        except Exception as e:
            logger.error(f"获取配置详情失败: key={key}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_all_with_details() -> Dict[str, Dict[str, Any]]:
        """获取所有配置项的详细信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有配置项的详细信息，键为配置项键名
        """
        from .database import SessionLocal, init_database_config
        import pytz
        init_database_config()
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).all()
            result = {}
            
            def format_datetime(dt):
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            for config in configs:
                result[config.key] = {
                    "key": config.key,
                    "value": config.value,
                    "description": config.description,
                    "plugin": config.plugin,
                    "name": config.name,
                    "is_sensitive": config.is_sensitive,
                    "created_at": format_datetime(config.created_at),
                    "updated_at": format_datetime(config.updated_at)
                }
            return result
        except Exception as e:
            logger.error(f"获取所有配置详情失败: error={e}")
            return {}
        finally:
            db.close()


class TaskBusiness:
    """任务模型类
    
    用于操作tasks表，提供CRUD操作方法
    兼容SQLite和DuckDB
    """
    
    @staticmethod
    def create(task_id: str, task_type: str, params: Dict[str, Any]) -> bool:
        """创建新任务
        
        Args:
            task_id: 任务ID
            task_type: 任务类型
            params: 任务参数
            
        Returns:
            bool: 创建成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        import json
        db: Session = SessionLocal()
        try:
            # 序列化参数为JSON字符串
            params_json = json.dumps(params)
            
            task = Task(
                task_id=task_id,
                task_type=task_type,
                status="pending",
                params=params_json
            )
            db.add(task)
            db.commit()
            logger.info(f"任务已创建: task_id={task_id}, task_type={task_type}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"创建任务失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def start(task_id: str) -> bool:
        """开始任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(Task).filter_by(task_id=task_id).first()
            if task:
                task.status = "running"
                task.start_time = func.now()
                db.commit()
                logger.info(f"任务已开始: task_id={task_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"开始任务失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def update_progress(task_id: str, current: str, completed: int, total: int, failed: int = 0, status: str = None) -> bool:
        """更新任务进度
        
        Args:
            task_id: 任务ID
            current: 当前处理的项目
            completed: 已完成的项目数
            total: 总项目数
            failed: 失败的项目数
            status: 可选的状态描述
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(Task).filter_by(task_id=task_id).first()
            if task:
                # 计算进度百分比
                percentage = 0
                if total > 0:
                    percentage = int((completed + failed) / total * 100)
                
                task.total = total
                task.completed = completed
                task.failed = failed
                task.current = current
                task.percentage = percentage
                
                db.commit()
                logger.debug(f"任务进度已更新: task_id={task_id}, current={current}, progress={percentage}%")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新任务进度失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def complete(task_id: str) -> bool:
        """完成任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(Task).filter_by(task_id=task_id).first()
            if task:
                task.status = "completed"
                task.end_time = func.now()
                db.commit()
                logger.info(f"任务已完成: task_id={task_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"完成任务失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def fail(task_id: str, error_message: str) -> bool:
        """标记任务失败
        
        Args:
            task_id: 任务ID
            error_message: 错误信息
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(Task).filter_by(task_id=task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_message
                task.end_time = func.now()
                db.commit()
                logger.error(f"任务已失败: task_id={task_id}, error={error_message}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"标记任务失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get(task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Dict[str, Any]]: 任务信息，如果不存在则返回None
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        import json
        import pytz
        db: Session = SessionLocal()
        try:
            task = db.query(Task).filter_by(task_id=task_id).first()
            if not task:
                return None
            
            def format_datetime(dt):
                """格式化datetime对象，转换为上海时区"""
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            # 解析结果
            task_info = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": task.status,
                "progress": {
                    "total": task.total,
                    "completed": task.completed,
                    "failed": task.failed,
                    "current": task.current,
                    "percentage": task.percentage
                },
                "params": json.loads(task.params),
                "start_time": format_datetime(task.start_time),
                "end_time": format_datetime(task.end_time),
                "error_message": task.error_message,
                "created_at": format_datetime(task.created_at),
                "updated_at": format_datetime(task.updated_at)
            }
            
            return task_info
        except Exception as e:
            logger.error(f"获取任务信息失败: task_id={task_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_all() -> Dict[str, Dict[str, Any]]:
        """
        获取所有任务信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有任务信息，键为任务ID
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        import json
        import pytz
        db: Session = SessionLocal()
        try:
            tasks = db.query(Task).order_by(Task.created_at.desc()).all()
            
            def format_datetime(dt):
                """格式化datetime对象，转换为上海时区"""
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            result = {}
            for task in tasks:
                result[task.task_id] = {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "progress": {
                        "total": task.total,
                        "completed": task.completed,
                        "failed": task.failed,
                        "current": task.current,
                        "percentage": task.percentage
                    },
                    "params": json.loads(task.params),
                    "start_time": format_datetime(task.start_time),
                    "end_time": format_datetime(task.end_time),
                    "error_message": task.error_message,
                    "created_at": format_datetime(task.created_at),
                    "updated_at": format_datetime(task.updated_at)
                }
            
            return result
        except Exception as e:
            logger.error(f"获取所有任务信息失败: error={e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def get_paginated(page: int = 1, page_size: int = 10, filters: dict = None, sort_by: str = "created_at", sort_order: str = "desc") -> dict:
        """
        获取分页任务列表
        
        Args:
            page: 当前页码，默认1
            page_size: 每页数量，默认10
            filters: 过滤条件，支持task_type、status、start_time、end_time、created_at、updated_at
            sort_by: 排序字段，默认created_at
            sort_order: 排序顺序，asc或desc，默认desc
            
        Returns:
            dict: 包含任务列表和分页信息的字典
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        import json
        db: Session = SessionLocal()
        try:
            # 构建查询
            query = db.query(Task)
            
            # 应用过滤条件
            if filters:
                # 任务类型过滤
                if "task_type" in filters and filters["task_type"]:
                    query = query.filter(Task.task_type == filters["task_type"])
                
                # 任务状态过滤
                if "status" in filters and filters["status"]:
                    query = query.filter(Task.status == filters["status"])
                
                # 开始时间过滤
                if "start_time" in filters and filters["start_time"]:
                    query = query.filter(Task.start_time >= filters["start_time"])
                
                # 结束时间过滤
                if "end_time" in filters and filters["end_time"]:
                    query = query.filter(Task.end_time <= filters["end_time"])
                
                # 创建时间过滤
                if "created_at" in filters and filters["created_at"]:
                    query = query.filter(Task.created_at >= filters["created_at"])
                
                # 更新时间过滤
                if "updated_at" in filters and filters["updated_at"]:
                    query = query.filter(Task.updated_at <= filters["updated_at"])
            
            # 计算总记录数
            total = query.count()
            
            # 验证排序字段，防止SQL注入
            allowed_sort_fields = ["task_id", "task_type", "status", "start_time", "end_time", "created_at", "updated_at"]
            if sort_by not in allowed_sort_fields:
                sort_by = "created_at"
            
            # 验证排序顺序
            if sort_order not in ["asc", "desc"]:
                sort_order = "desc"
            
            # 应用排序和分页
            if sort_order == "desc":
                query = query.order_by(getattr(Task, sort_by).desc())
            else:
                query = query.order_by(getattr(Task, sort_by).asc())
            
            # 计算分页参数
            offset = (page - 1) * page_size
            paginated_tasks = query.offset(offset).limit(page_size).all()
            
            # 处理结果
            def format_datetime(dt):
                """格式化datetime对象，转换为上海时区"""
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            tasks = []
            for task in paginated_tasks:
                tasks.append({
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "progress": {
                        "total": task.total,
                        "completed": task.completed,
                        "failed": task.failed,
                        "current": task.current,
                        "percentage": task.percentage
                    },
                    "params": json.loads(task.params),
                    "start_time": format_datetime(task.start_time),
                    "end_time": format_datetime(task.end_time),
                    "error_message": task.error_message,
                    "created_at": format_datetime(task.created_at),
                    "updated_at": format_datetime(task.updated_at)
                })
            
            # 计算总页数
            pages = (total + page_size - 1) // page_size
            
            return {
                "tasks": tasks,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "pages": pages
                }
            }
        except Exception as e:
            logger.error(f"获取分页任务列表失败: error={e}")
            return {
                "tasks": [],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "pages": 0
                }
            }
        finally:
            db.close()
    
    @staticmethod
    def delete(task_id: str) -> bool:
        """删除任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(Task).filter_by(task_id=task_id).first()
            if task:
                db.delete(task)
                db.commit()
                logger.info(f"任务已删除: task_id={task_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除任务失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()


class DataPoolBusiness:
    """资产池模型类
    
    用于操作data_pools和data_pool_assets表，提供CRUD操作方法
    """
    
    @staticmethod
    def create(name: str, type: str = "", description: str = "", color: str = "", tags: list = None, is_public: bool = True, is_default: bool = False) -> Optional[int]:
        """
        创建资产池
        
        Args:
            name: 资产池名称
            type: 资产池类型
            description: 资产池描述
            color: 资产池颜色
            tags: 资产池标签
            is_public: 是否公开
            is_default: 是否为默认资产池
            
        Returns:
            Optional[int]: 创建成功返回资产池ID，失败返回None
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 检查是否已经存在相同名称和类型的资产池
            existing_pool = db.query(DataPool).filter_by(name=name, type=type).first()
            if existing_pool:
                logger.error(f"创建资产池失败: 已存在相同名称和类型的资产池: name={name}, type={type}")
                return None
            
            # 如果设置为默认资产池，先将其他默认资产池设置为非默认
            if is_default:
                db.query(DataPool).filter_by(is_default=True).update({"is_default": False})
            
            # 获取当前最大id值，手动生成新id
            max_id_result = db.query(func.max(DataPool.id)).first()
            new_id = (max_id_result[0] + 1) if max_id_result[0] is not None else 1
            
            # 创建资产池
            pool = DataPool(
                id=new_id,
                name=name,
                type=type,
                description=description,
                color=color,
                tags=json.dumps(tags) if tags else None,
                is_public=is_public,
                is_default=is_default
            )
            db.add(pool)
            db.commit()
            db.refresh(pool)
            
            logger.info(f"资产池已创建: id={pool.id}, name={name}, type={type}")
            return pool.id
        except Exception as e:
            db.rollback()
            logger.error(f"创建资产池失败: name={name}, type={type}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def update(pool_id: int, name: str = None, type: str = None, description: str = None, color: str = None, tags: list = None, is_public: bool = None, is_default: bool = None) -> bool:
        """
        更新资产池
        
        Args:
            pool_id: 资产池ID
            name: 资产池名称
            type: 资产池类型
            description: 资产池描述
            color: 资产池颜色
            tags: 资产池标签
            is_public: 是否公开
            is_default: 是否为默认资产池
            
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            pool = db.query(DataPool).filter_by(id=pool_id).first()
            if not pool:
                logger.error(f"资产池不存在: pool_id={pool_id}")
                return False
            
            # 检查是否要更新name或type，如果是，需要检查是否已经存在相同名称和类型的资产池
            if name is not None or type is not None:
                # 确定要使用的name和type值
                new_name = name if name is not None else pool.name
                new_type = type if type is not None else pool.type
                
                # 检查是否已经存在相同名称和类型的资产池，并且该资产池的id不是当前要更新的资产池的id
                existing_pool = db.query(DataPool).filter_by(name=new_name, type=new_type).filter(DataPool.id != pool_id).first()
                if existing_pool:
                    logger.error(f"更新资产池失败: 已存在相同名称和类型的资产池: name={new_name}, type={new_type}")
                    return False
            
            # 如果设置为默认资产池，先将其他默认资产池设置为非默认
            if is_default is True:
                db.query(DataPool).filter_by(is_default=True).update({"is_default": False})
                pool.is_default = True
            elif is_default is not None:
                pool.is_default = is_default
            
            # 更新其他字段
            if name is not None:
                pool.name = name
            if type is not None:
                pool.type = type
            if description is not None:
                pool.description = description
            if color is not None:
                pool.color = color
            if tags is not None:
                pool.tags = json.dumps(tags)
            if is_public is not None:
                pool.is_public = is_public
            
            db.commit()
            logger.info(f"资产池已更新: pool_id={pool_id}, name={pool.name}, type={pool.type}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新资产池失败: pool_id={pool_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def delete(pool_id: int) -> bool:
        """删除资产池
        
        Args:
            pool_id: 资产池ID
            
        Returns:
            bool: 删除成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 删除资产池关联的资产
            db.query(DataPoolAsset).filter_by(pool_id=pool_id).delete()
            
            # 删除资产池
            pool = db.query(DataPool).filter_by(id=pool_id).first()
            if pool:
                db.delete(pool)
                db.commit()
                logger.info(f"资产池已删除: pool_id={pool_id}, name={pool.name}")
            
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除资产池失败: pool_id={pool_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def add_asset(pool_id: int, asset_id: str, asset_type: str) -> bool:
        """向资产池添加资产
        
        Args:
            pool_id: 资产池ID
            asset_id: 资产ID（股票代码或加密货币对）
            asset_type: 资产类型（stock/crypto）
            
        Returns:
            bool: 添加成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 检查资产池是否存在
            pool = db.query(DataPool).filter_by(id=pool_id).first()
            if not pool:
                logger.error(f"资产池不存在: pool_id={pool_id}")
                return False
            
            # 检查资产是否已存在于资产池中
            existing_asset = db.query(DataPoolAsset).filter_by(pool_id=pool_id, asset_id=asset_id).first()
            if existing_asset:
                logger.warning(f"资产已存在于资产池中: pool_id={pool_id}, asset_id={asset_id}")
                return True
            
            # 添加资产到资产池
            pool_asset = DataPoolAsset(
                pool_id=pool_id,
                asset_id=asset_id,
                asset_type=asset_type
            )
            db.add(pool_asset)
            db.commit()
            
            logger.info(f"资产已添加到资产池: pool_id={pool_id}, asset_id={asset_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"添加资产到资产池失败: pool_id={pool_id}, asset_id={asset_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def add_assets(pool_id: int, assets: list, asset_type: str) -> bool:
        """
        批量向资产池添加资产
        
        Args:
            pool_id: 资产池ID
            assets: 资产列表（股票代码或加密货币对）
            asset_type: 资产类型（stock/crypto）
            
        Returns:
            bool: 批量添加成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 检查资产池是否存在
            pool = db.query(DataPool).filter_by(id=pool_id).first()
            if not pool:
                logger.error(f"资产池不存在: pool_id={pool_id}")
                return False
            
            # 先删除该资产池的所有现有资产，然后添加新的资产
            # 这样可以确保资产池内的资产数量正确
            db.query(DataPoolAsset).filter_by(pool_id=pool_id).delete()
            
            # 批量添加资产，使用ORM方式
            pool_assets = []
            for asset_id in assets:
                pool_asset = DataPoolAsset(
                    pool_id=pool_id,
                    asset_id=asset_id,
                    asset_type=asset_type
                )
                pool_assets.append(pool_asset)
            
            # 批量添加到会话
            db.add_all(pool_assets)
            db.commit()
            logger.info(f"批量更新资产池资产成功: pool_id={pool_id}, asset_count={len(assets)}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"批量更新资产池资产失败: pool_id={pool_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def remove_asset(pool_id: int, asset_id: str) -> bool:
        """从资产池移除资产
        
        Args:
            pool_id: 资产池ID
            asset_id: 资产ID（股票代码或加密货币对）
            
        Returns:
            bool: 移除成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 检查资产是否存在于资产池中
            existing_asset = db.query(DataPoolAsset).filter_by(pool_id=pool_id, asset_id=asset_id).first()
            if existing_asset:
                db.delete(existing_asset)
                db.commit()
                logger.info(f"资产已从资产池移除: pool_id={pool_id}, asset_id={asset_id}")
            
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"从资产池移除资产失败: pool_id={pool_id}, asset_id={asset_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def remove_assets(pool_id: int, assets: list) -> bool:
        """批量从资产池移除资产
        
        Args:
            pool_id: 资产池ID
            assets: 资产列表（股票代码或加密货币对）
            
        Returns:
            bool: 批量移除成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 批量移除资产
            for asset_id in assets:
                db.query(DataPoolAsset).filter_by(pool_id=pool_id, asset_id=asset_id).delete()
            
            db.commit()
            logger.info(f"批量从资产池移除资产成功: pool_id={pool_id}, asset_count={len(assets)}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"批量从资产池移除资产失败: pool_id={pool_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_all(type: str = None) -> list:
        """
        获取所有资产池，支持按类型过滤
        
        Args:
            type: 资产池类型过滤
            
        Returns:
            list: 资产池列表
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        import pytz
        db: Session = SessionLocal()
        try:
            query = db.query(DataPool)
            if type:
                query = query.filter_by(type=type)
            
            def format_datetime(dt):
                """格式化datetime对象，转换为上海时区"""
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            pools = query.all()
            result = []
            for pool in pools:
                # 获取资产池包含的资产数量，使用func.count()直接计算行数，避免使用id字段
                asset_count = db.query(func.count()).select_from(DataPoolAsset).filter_by(pool_id=pool.id).scalar() or 0
                
                result.append({
                    "id": pool.id,
                    "name": pool.name,
                    "type": pool.type,
                    "description": pool.description,
                    "color": pool.color,
                    "tags": json.loads(pool.tags) if pool.tags else [],
                    "is_public": pool.is_public,
                    "is_default": pool.is_default,
                    "asset_count": asset_count,
                    "created_at": format_datetime(pool.created_at),
                    "updated_at": format_datetime(pool.updated_at)
                })
            return result
        except Exception as e:
            logger.error(f"获取所有资产池失败: type={type}, error={e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get(pool_id: int) -> dict:
        """
        获取指定ID的资产池
        
        Args:
            pool_id: 资产池ID
            
        Returns:
            dict: 资产池详情
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            pool = db.query(DataPool).filter_by(id=pool_id).first()
            if not pool:
                return None
            
            import pytz
            def format_datetime(dt):
                """格式化datetime对象，转换为上海时区"""
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取资产池包含的资产数量，使用func.count()直接计算行数，避免使用id字段
            asset_count = db.query(func.count()).select_from(DataPoolAsset).filter_by(pool_id=pool.id).scalar() or 0
            
            return {
                "id": pool.id,
                "name": pool.name,
                "type": pool.type,
                "description": pool.description,
                "color": pool.color,
                "tags": json.loads(pool.tags) if pool.tags else [],
                "is_public": pool.is_public,
                "is_default": pool.is_default,
                "asset_count": asset_count,
                "created_at": format_datetime(pool.created_at),
                "updated_at": format_datetime(pool.updated_at)
            }
        except Exception as e:
            logger.error(f"获取资产池失败: pool_id={pool_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_assets(pool_id: int) -> list:
        """
        获取资产池包含的资产列表
        
        Args:
            pool_id: 资产池ID
            
        Returns:
            list: 资产列表（股票代码或加密货币对）
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            assets = db.query(DataPoolAsset).filter_by(pool_id=pool_id).all()
            return [asset.asset_id for asset in assets]
        except Exception as e:
            logger.error(f"获取资产池资产列表失败: pool_id={pool_id}, error={e}")
            return []
        finally:
            db.close()


class ScheduledTaskBusiness:
    """定时任务模型类
    
    用于操作scheduled_tasks表，提供CRUD操作方法
    """
    
    @staticmethod
    def create(
        name: str,
        description: str = "",
        task_type: str = "download_crypto",
        cron_expression: Optional[str] = None,
        interval: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        frequency_type: Optional[str] = None,
        symbols: Optional[list] = None,
        exchange: Optional[str] = None,
        candle_type: str = "spot",
        save_dir: Optional[str] = None,
        max_workers: int = 1,
        incremental_enabled: bool = True,
        notification_enabled: bool = False,
        notification_type: Optional[str] = None,
        notification_email: Optional[str] = None,
        notification_webhook: Optional[str] = None,
        created_by: str = "system"
    ) -> Optional[int]:
        """
        创建定时任务
        
        Args:
            name: 任务名称
            description: 任务描述
            task_type: 任务类型
            cron_expression: CRON表达式
            interval: 时间间隔
            start_time: 开始执行时间
            end_time: 结束执行时间
            frequency_type: 频率类型
            symbols: 交易对列表
            exchange: 交易所
            candle_type: 蜡烛图类型
            save_dir: 保存目录
            max_workers: 最大工作线程数
            incremental_enabled: 是否启用增量采集
            notification_enabled: 是否启用通知
            notification_type: 通知类型
            notification_email: 通知邮箱
            notification_webhook: 通知Webhook
            created_by: 创建者
            
        Returns:
            Optional[int]: 创建成功返回任务ID，失败返回None
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 获取当前最大id值，手动生成新id
            max_id_result = db.query(func.max(ScheduledTask.id)).first()
            new_id = (max_id_result[0] + 1) if max_id_result[0] is not None else 1
            
            # 创建定时任务
            task = ScheduledTask(
                id=new_id,
                name=name,
                description=description,
                task_type=task_type,
                status="pending",
                cron_expression=cron_expression,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                frequency_type=frequency_type,
                symbols=json.dumps(symbols) if symbols else None,
                exchange=exchange,
                candle_type=candle_type,
                save_dir=save_dir,
                max_workers=max_workers,
                incremental_enabled=incremental_enabled,
                notification_enabled=notification_enabled,
                notification_type=notification_type,
                notification_email=notification_email,
                notification_webhook=notification_webhook,
                created_by=created_by
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            
            logger.info(f"定时任务已创建: id={task.id}, name={name}")
            return task.id
        except Exception as e:
            db.rollback()
            logger.error(f"创建定时任务失败: name={name}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get(task_id: int) -> Optional[Dict[str, Any]]:
        """
        获取定时任务详情
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Dict[str, Any]]: 任务详情，如果不存在则返回None
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter_by(id=task_id).first()
            if not task:
                return None
            
            import pytz
            def format_datetime(dt):
                """格式化datetime对象，转换为上海时区"""
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            return {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "task_type": task.task_type,
                "status": task.status,
                "cron_expression": task.cron_expression,
                "interval": task.interval,
                "start_time": format_datetime(task.start_time),
                "end_time": format_datetime(task.end_time),
                "frequency_type": task.frequency_type,
                "symbols": json.loads(task.symbols) if task.symbols else [],
                "exchange": task.exchange,
                "candle_type": task.candle_type,
                "save_dir": task.save_dir,
                "max_workers": task.max_workers,
                "incremental_enabled": task.incremental_enabled,
                "last_collected_date": format_datetime(task.last_collected_date),
                "notification_enabled": task.notification_enabled,
                "notification_type": task.notification_type,
                "notification_email": task.notification_email,
                "notification_webhook": task.notification_webhook,
                "last_run_time": format_datetime(task.last_run_time),
                "next_run_time": format_datetime(task.next_run_time),
                "last_result": task.last_result,
                "error_message": task.error_message,
                "run_count": task.run_count,
                "success_count": task.success_count,
                "fail_count": task.fail_count,
                "created_at": format_datetime(task.created_at),
                "updated_at": format_datetime(task.updated_at),
                "created_by": task.created_by
            }
        except Exception as e:
            logger.error(f"获取定时任务失败: task_id={task_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_all(filters: dict = None) -> Dict[str, Dict[str, Any]]:
        """
        获取所有定时任务
        
        Args:
            filters: 过滤条件
            
        Returns:
            Dict[str, Dict[str, Any]]: 所有定时任务，键为任务ID
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            query = db.query(ScheduledTask)
            
            # 应用过滤条件
            if filters:
                # 状态过滤，支持单个状态值或状态列表
                if "status" in filters and filters["status"]:
                    status = filters["status"]
                    if isinstance(status, list):
                        # 如果是列表，使用 in_ 操作符
                        query = query.filter(ScheduledTask.status.in_(status))
                    else:
                        # 否则使用相等比较
                        query = query.filter(ScheduledTask.status == status)
                
                # 任务类型过滤，支持单个任务类型或任务类型列表
                if "task_type" in filters and filters["task_type"]:
                    task_type = filters["task_type"]
                    if isinstance(task_type, list):
                        # 如果是列表，使用 in_ 操作符
                        query = query.filter(ScheduledTask.task_type.in_(task_type))
                    else:
                        # 否则使用相等比较
                        query = query.filter(ScheduledTask.task_type == task_type)
            
            tasks = query.all()
            result = {}
            
            import pytz
            def format_datetime(dt):
                """格式化datetime对象，转换为上海时区"""
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            for task in tasks:
                result[task.id] = {
                    "id": task.id,
                    "name": task.name,
                    "description": task.description,
                    "task_type": task.task_type,
                    "status": task.status,
                    "cron_expression": task.cron_expression,
                    "interval": task.interval,
                    "start_time": format_datetime(task.start_time),
                    "end_time": format_datetime(task.end_time),
                    "frequency_type": task.frequency_type,
                    "symbols": json.loads(task.symbols) if task.symbols else [],
                    "exchange": task.exchange,
                    "candle_type": task.candle_type,
                    "save_dir": task.save_dir,
                    "max_workers": task.max_workers,
                    "incremental_enabled": task.incremental_enabled,
                    "last_collected_date": format_datetime(task.last_collected_date),
                    "notification_enabled": task.notification_enabled,
                    "notification_type": task.notification_type,
                    "notification_email": task.notification_email,
                    "notification_webhook": task.notification_webhook,
                    "last_run_time": format_datetime(task.last_run_time),
                    "next_run_time": format_datetime(task.next_run_time),
                    "last_result": task.last_result,
                    "error_message": task.error_message,
                    "run_count": task.run_count,
                    "success_count": task.success_count,
                    "fail_count": task.fail_count,
                    "created_at": format_datetime(task.created_at),
                    "updated_at": format_datetime(task.updated_at),
                    "created_by": task.created_by
                }
            
            return result
        except Exception as e:
            logger.error(f"获取所有定时任务失败: error={e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def update(
        task_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        cron_expression: Optional[str] = None,
        interval: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        frequency_type: Optional[str] = None,
        symbols: Optional[list] = None,
        exchange: Optional[str] = None,
        candle_type: Optional[str] = None,
        save_dir: Optional[str] = None,
        max_workers: Optional[int] = None,
        incremental_enabled: Optional[bool] = None,
        notification_enabled: Optional[bool] = None,
        notification_type: Optional[str] = None,
        notification_email: Optional[str] = None,
        notification_webhook: Optional[str] = None,
        # 添加缺失的参数
        last_run_time: Optional[datetime] = None,
        next_run_time: Optional[datetime] = None,
        last_result: Optional[str] = None,
        error_message: Optional[str] = None,
        run_count: Optional[int] = None,
        success_count: Optional[int] = None,
        fail_count: Optional[int] = None,
        last_collected_date: Optional[datetime] = None
    ) -> bool:
        """
        更新定时任务
        
        Args:
            task_id: 任务ID
            name: 任务名称
            description: 任务描述
            status: 任务状态
            cron_expression: CRON表达式
            interval: 时间间隔
            start_time: 开始执行时间
            end_time: 结束执行时间
            frequency_type: 频率类型
            symbols: 交易对列表
            exchange: 交易所
            candle_type: 蜡烛图类型
            save_dir: 保存目录
            max_workers: 最大工作线程数
            incremental_enabled: 是否启用增量采集
            notification_enabled: 是否启用通知
            notification_type: 通知类型
            notification_email: 通知邮箱
            notification_webhook: 通知Webhook
            
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter_by(id=task_id).first()
            if not task:
                logger.error(f"定时任务不存在: task_id={task_id}")
                return False
            
            # 更新字段
            if name is not None:
                task.name = name
            if description is not None:
                task.description = description
            if status is not None:
                task.status = status
            if cron_expression is not None:
                task.cron_expression = cron_expression
            if interval is not None:
                task.interval = interval
            if start_time is not None:
                task.start_time = start_time
            if end_time is not None:
                task.end_time = end_time
            if frequency_type is not None:
                task.frequency_type = frequency_type
            if symbols is not None:
                task.symbols = json.dumps(symbols)
            if exchange is not None:
                task.exchange = exchange
            if candle_type is not None:
                task.candle_type = candle_type
            if save_dir is not None:
                task.save_dir = save_dir
            if max_workers is not None:
                task.max_workers = max_workers
            if incremental_enabled is not None:
                task.incremental_enabled = incremental_enabled
            if notification_enabled is not None:
                task.notification_enabled = notification_enabled
            if notification_type is not None:
                task.notification_type = notification_type
            if notification_email is not None:
                task.notification_email = notification_email
            if notification_webhook is not None:
                task.notification_webhook = notification_webhook
            # 处理新增的参数
            if last_run_time is not None:
                task.last_run_time = last_run_time
            if next_run_time is not None:
                task.next_run_time = next_run_time
            if last_result is not None:
                task.last_result = last_result
            if error_message is not None:
                task.error_message = error_message
            if run_count is not None:
                task.run_count = run_count
            if success_count is not None:
                task.success_count = success_count
            if fail_count is not None:
                task.fail_count = fail_count
            if last_collected_date is not None:
                task.last_collected_date = last_collected_date
            
            db.commit()
            logger.info(f"定时任务已更新: task_id={task_id}, name={task.name}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新定时任务失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def delete(task_id: int) -> bool:
        """
        删除定时任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 删除成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter_by(id=task_id).first()
            if task:
                db.delete(task)
                db.commit()
                logger.info(f"定时任务已删除: task_id={task_id}, name={task.name}")
            
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除定时任务失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def update_execution_status(
        task_id: int,
        status: str,
        last_result: Optional[str] = None,
        error_message: Optional[str] = None,
        last_run_time: Optional[datetime] = None,
        next_run_time: Optional[datetime] = None,
        last_collected_date: Optional[datetime] = None
    ) -> bool:
        """
        更新任务执行状态
        
        Args:
            task_id: 任务ID
            status: 任务状态
            last_result: 上次执行结果
            error_message: 错误信息
            last_run_time: 上次执行时间
            next_run_time: 下次执行时间
            last_collected_date: 上次采集日期
            
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        from .database import SessionLocal, init_database_config
        init_database_config()
        db: Session = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter_by(id=task_id).first()
            if not task:
                logger.error(f"定时任务不存在: task_id={task_id}")
                return False
            
            # 更新执行状态
            if status is not None:
                task.status = status
            if last_result is not None:
                task.last_result = last_result
            if error_message is not None:
                task.error_message = error_message
            if last_run_time is not None:
                task.last_run_time = last_run_time
                # 增加执行次数
                task.run_count += 1
                if last_result == "success":
                    task.success_count += 1
                elif last_result == "failed":
                    task.fail_count += 1
            if next_run_time is not None:
                task.next_run_time = next_run_time
            if last_collected_date is not None:
                task.last_collected_date = last_collected_date
            
            db.commit()
            logger.info(f"定时任务执行状态已更新: task_id={task_id}, status={status}, last_result={last_result}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新定时任务执行状态失败: task_id={task_id}, error={e}")
            return False
        finally:
            db.close()