# 数据库模型定义

from datetime import datetime
from typing import Optional, Dict, Any
from .connection import get_db_connection
from loguru import logger

# SQLAlchemy模型定义
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Float
from sqlalchemy.sql import func
from .database import Base


# SQLAlchemy模型类
class SystemConfig(Base):
    """系统配置SQLAlchemy模型
    
    对应system_config表的SQLAlchemy模型定义
    """
    __tablename__ = "system_config"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
    description = Column(Text, nullable=True)
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
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    feature_name = Column(String, nullable=False, index=True)
    freq = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class DataPool(Base):
    """资产池SQLAlchemy模型
    
    对应data_pools表的SQLAlchemy模型定义，用于存储资产池信息
    """
    __tablename__ = "data_pools"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, index=True)
    type = Column(String, index=True)  # stock/crypto
    description = Column(Text, nullable=True)
    color = Column(String, default="#409EFF")  # 卡片颜色
    tags = Column(String, nullable=True)  # 标签，JSON格式存储
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class DataPoolAsset(Base):
    """资产池资产关联SQLAlchemy模型
    
    对应data_pool_assets表的SQLAlchemy模型定义，用于存储资产池与资产的关联关系
    """
    __tablename__ = "data_pool_assets"
    
    pool_id = Column(Integer, ForeignKey("data_pools.id"), primary_key=True)
    asset_id = Column(String, primary_key=True)  # 股票代码或加密货币对
    asset_type = Column(String)  # stock/crypto
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Kline(Base):
    """K线数据SQLAlchemy模型
    
    对应klines表的SQLAlchemy模型定义，用于存储加密货币K线数据
    """
    __tablename__ = "klines"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    interval = Column(String, nullable=False, index=True)
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # 设置唯一约束，确保symbol + interval + date的组合唯一
    __table_args__ = (
        Column(
            "unique_kline", 
            String,
            primary_key=False,
            default=lambda context: f"{context.current_parameters.get('symbol')}_{context.current_parameters.get('interval')}_{context.current_parameters.get('date').isoformat()}",
            unique=True
        ),
    )


# 从database.py导入SessionLocal和相关依赖
from .database import SessionLocal
from sqlalchemy.orm import Session

# 保留现有的业务逻辑类，确保向后兼容
class SystemConfigBusiness:
    """系统配置模型类
    
    用于操作system_config表，提供CRUD操作方法
    """
    
    @staticmethod
    def get(key: str) -> Optional[str]:
        """获取指定键的配置值
        
        Args:
            key: 配置键名
            
        Returns:
            Optional[str]: 配置值，如果不存在则返回None
        """
        # 初始化数据库配置，确保SessionLocal已绑定引擎
        from .database import init_database_config
        init_database_config()
        
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            return config.value if config else None
        except Exception as e:
            logger.error(f"获取配置失败: key={key}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_all() -> Dict[str, str]:
        """获取所有配置
        
        Returns:
            Dict[str, str]: 所有配置的字典，键为配置名，值为配置值
        """
        # 初始化数据库配置，确保SessionLocal已绑定引擎
        from .database import init_database_config
        init_database_config()
        
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).order_by(SystemConfig.key).all()
            return {config.key: config.value for config in configs}
        except Exception as e:
            logger.error(f"获取所有配置失败: error={e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def set(key: str, value: str, description: Optional[str] = None) -> bool:
        """设置配置值
        
        Args:
            key: 配置键名
            value: 配置值
            description: 配置描述，可选
            
        Returns:
            bool: 设置成功返回True，失败返回False
        """
        # 初始化数据库配置，确保SessionLocal已绑定引擎
        from .database import init_database_config
        init_database_config()
        
        db: Session = SessionLocal()
        try:
            # 查询是否存在该配置
            config = db.query(SystemConfig).filter_by(key=key).first()
            
            if config:
                # 如果存在，更新配置
                config.value = value
                if description is not None:
                    config.description = description
            else:
                # 如果不存在，创建新配置
                config = SystemConfig(key=key, value=value, description=description)
                db.add(config)
            
            # 提交更改
            db.commit()
            logger.info(f"配置已更新: key={key}, value={value}")
            return True
        except Exception as e:
            # 回滚事务
            db.rollback()
            logger.error(f"设置配置失败: key={key}, value={value}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def delete(key: str) -> bool:
        """删除指定键的配置
        
        Args:
            key: 配置键名
            
        Returns:
            bool: 删除成功返回True，失败返回False
        """
        # 初始化数据库配置，确保SessionLocal已绑定引擎
        from .database import init_database_config
        init_database_config()
        
        db: Session = SessionLocal()
        try:
            # 查询是否存在该配置
            config = db.query(SystemConfig).filter_by(key=key).first()
            
            if config:
                # 如果存在，删除配置
                db.delete(config)
                db.commit()
                logger.info(f"配置已删除: key={key}")
                return True
            else:
                # 如果不存在，返回True表示操作成功
                logger.info(f"配置不存在，无需删除: key={key}")
                return True
        except Exception as e:
            # 回滚事务
            db.rollback()
            logger.error(f"删除配置失败: key={key}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_with_details(key: str) -> Optional[Dict[str, Any]]:
        """获取配置的详细信息
        
        Args:
            key: 配置键名
            
        Returns:
            Optional[Dict[str, Any]]: 配置的详细信息，包括键、值、描述、创建时间和更新时间
        """
        # 初始化数据库配置，确保SessionLocal已绑定引擎
        from .database import init_database_config
        init_database_config()
        
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                return {
                    "key": config.key,
                    "value": config.value,
                    "description": config.description,
                    "created_at": config.created_at,
                    "updated_at": config.updated_at
                }
            return None
        except Exception as e:
            logger.error(f"获取配置详情失败: key={key}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_all_with_details() -> Dict[str, Dict[str, Any]]:
        """获取所有配置的详细信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有配置的详细信息，键为配置名，值为配置详情字典
        """
        try:
            # 初始化数据库配置，确保数据库连接正常
            from .database import init_database_config
            init_database_config()
            
            conn = get_db_connection()
            results = conn.execute(
                "SELECT key, value, description, created_at, updated_at FROM system_config ORDER BY key"
            ).fetchall()
            return {
                row[0]: {
                    "key": row[0],
                    "value": row[1],
                    "description": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
                for row in results
            }
        except Exception as e:
            logger.error(f"获取所有配置详情失败: error={e}")
            return {}


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
        try:
            import json
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            # 序列化参数为JSON字符串
            params_json = json.dumps(params)
            
            conn.execute("""
            INSERT INTO tasks (task_id, task_type, status, params)
            VALUES (?, ?, ?, ?)
            """, (task_id, task_type, "pending", params_json))
            
            logger.info(f"任务已创建: task_id={task_id}, task_type={task_type}")
            return True
        except Exception as e:
            logger.error(f"创建任务失败: task_id={task_id}, error={e}")
            return False
    
    @staticmethod
    def start(task_id: str) -> bool:
        """开始任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        try:
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            conn.execute("""
            UPDATE tasks 
            SET status = ?, start_time = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """, ("running", task_id))
            
            logger.info(f"任务已开始: task_id={task_id}")
            return True
        except Exception as e:
            logger.error(f"开始任务失败: task_id={task_id}, error={e}")
            return False
    
    @staticmethod
    def update_progress(task_id: str, current: str, completed: int, total: int, failed: int = 0, status: str = None) -> bool:
        """更新任务进度
        
        Args:
            task_id: 任务ID
            current: 当前处理的项目
            completed: 已完成的项目数
            total: 总项目数
            failed: 失败的项目数
            status: 详细的状态描述，例如"Downloaded 2025-11-01"
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        try:
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            # 计算进度百分比
            percentage = 0
            if total > 0:
                percentage = int((completed + failed) / total * 100)
            
            # 使用current字段存储详细状态描述
            detailed_current = f"{current} - {status}" if status else current
            
            conn.execute("""
            UPDATE tasks 
            SET 
                total = ?, 
                completed = ?, 
                failed = ?, 
                current = ?, 
                percentage = ?, 
                updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """, (total, completed, failed, detailed_current, percentage, task_id))
            
            logger.debug(f"任务进度已更新: task_id={task_id}, current={detailed_current}, progress={percentage}%")
            return True
        except Exception as e:
            logger.error(f"更新任务进度失败: task_id={task_id}, error={e}")
            return False
    
    @staticmethod
    def complete(task_id: str) -> bool:
        """完成任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        try:
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            conn.execute("""
            UPDATE tasks 
            SET status = ?, end_time = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """, ("completed", task_id))
            
            logger.info(f"任务已完成: task_id={task_id}")
            return True
        except Exception as e:
            logger.error(f"完成任务失败: task_id={task_id}, error={e}")
            return False
    
    @staticmethod
    def fail(task_id: str, error_message: str) -> bool:
        """标记任务失败
        
        Args:
            task_id: 任务ID
            error_message: 错误信息
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        try:
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            conn.execute("""
            UPDATE tasks 
            SET 
                status = ?, 
                error_message = ?, 
                end_time = CURRENT_TIMESTAMP, 
                updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """, ("failed", error_message, task_id))
            
            logger.error(f"任务已失败: task_id={task_id}, error={error_message}")
            return True
        except Exception as e:
            logger.error(f"标记任务失败: task_id={task_id}, error={e}")
            return False
    
    @staticmethod
    def get(task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Dict[str, Any]]: 任务信息，如果不存在则返回None
        """
        try:
            import json
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            result = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,)
            ).fetchone()
            
            if not result:
                return None
            
            # 解析结果
            task_info = {
                "task_id": result[0],
                "task_type": result[1],
                "status": result[2],
                "progress": {
                    "total": result[3],
                    "completed": result[4],
                    "failed": result[5],
                    "current": result[6],
                    "percentage": result[7],
                    "status": result[6]  # 使用current字段作为status，因为current字段已经包含了详细的状态描述
                },
                "params": json.loads(result[8]),
                "start_time": result[9],
                "end_time": result[10],
                "error_message": result[11],
                "created_at": result[12],
                "updated_at": result[13]
            }
            
            return task_info
        except Exception as e:
            logger.error(f"获取任务信息失败: task_id={task_id}, error={e}")
            return None
    
    @staticmethod
    def get_all() -> Dict[str, Dict[str, Any]]:
        """
        获取所有任务信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有任务信息，键为任务ID
        """
        try:
            import json
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            results = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC"
            ).fetchall()
            
            tasks = {}
            for result in results:
                task_id = result[0]
                tasks[task_id] = {
                "task_id": task_id,
                "task_type": result[1],
                "status": result[2],
                "progress": {
                    "total": result[3],
                    "completed": result[4],
                    "failed": result[5],
                    "current": result[6],
                    "percentage": result[7],
                    "status": result[6]  # 使用current字段作为status，包含详细的状态描述
                },
                "params": json.loads(result[8]),
                "start_time": result[9],
                "end_time": result[10],
                "error_message": result[11],
                "created_at": result[12],
                "updated_at": result[13]
            }
            
            return tasks
        except Exception as e:
            logger.error(f"获取所有任务信息失败: error={e}")
            return {}
    
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
        try:
            import json
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            # 构建查询条件
            where_clauses = []
            params = []
            
            if filters:
                # 任务类型过滤
                if "task_type" in filters and filters["task_type"]:
                    where_clauses.append("task_type = ?")
                    params.append(filters["task_type"])
                
                # 任务状态过滤
                if "status" in filters and filters["status"]:
                    where_clauses.append("status = ?")
                    params.append(filters["status"])
                
                # 开始时间过滤
                if "start_time" in filters and filters["start_time"]:
                    where_clauses.append("start_time >= ?")
                    params.append(filters["start_time"])
                
                # 结束时间过滤
                if "end_time" in filters and filters["end_time"]:
                    where_clauses.append("end_time <= ?")
                    params.append(filters["end_time"])
                
                # 创建时间过滤
                if "created_at" in filters and filters["created_at"]:
                    where_clauses.append("created_at >= ?")
                    params.append(filters["created_at"])
                
                # 更新时间过滤
                if "updated_at" in filters and filters["updated_at"]:
                    where_clauses.append("updated_at <= ?")
                    params.append(filters["updated_at"])
            
            # 构建WHERE子句
            where_sql = "" if not where_clauses else f"WHERE {' AND '.join(where_clauses)}"  
            
            # 构建排序子句
            # 验证排序字段，防止SQL注入
            allowed_sort_fields = ["task_id", "task_type", "status", "start_time", "end_time", "created_at", "updated_at"]
            if sort_by not in allowed_sort_fields:
                sort_by = "created_at"
            
            # 验证排序顺序
            if sort_order not in ["asc", "desc"]:
                sort_order = "desc"
            
            order_sql = f"ORDER BY {sort_by} {sort_order}"
            
            # 获取总记录数
            count_sql = f"SELECT COUNT(*) FROM tasks {where_sql}"
            total = conn.execute(count_sql, params).fetchone()[0]
            
            # 计算分页参数
            offset = (page - 1) * page_size
            
            # 构建分页查询SQL
            paginated_sql = f"SELECT * FROM tasks {where_sql} {order_sql} LIMIT ? OFFSET ?"
            params.extend([page_size, offset])
            
            # 执行查询
            results = conn.execute(paginated_sql, params).fetchall()
            
            # 处理结果
            tasks = []
            for result in results:
                task = {
                    "task_id": result[0],
                    "task_type": result[1],
                    "status": result[2],
                    "progress": {
                        "total": result[3],
                        "completed": result[4],
                        "failed": result[5],
                        "current": result[6],
                        "percentage": result[7],
                        "status": result[6]  # 使用current字段作为status，包含详细的状态描述
                    },
                    "params": json.loads(result[8]),
                    "start_time": result[9],
                    "end_time": result[10],
                    "error_message": result[11],
                    "created_at": result[12],
                    "updated_at": result[13]
                }
                tasks.append(task)
            
            # 计算总页数
            pages = (total + page_size - 1) // page_size
            
            # 返回结果
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
    
    @staticmethod
    def delete(task_id: str) -> bool:
        """删除任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 操作成功返回True，失败返回False
        """
        try:
            conn = get_db_connection()
            
            # 检查tasks表是否存在，如果不存在则初始化数据库
            try:
                conn.execute("SELECT 1 FROM tasks LIMIT 1")
            except Exception as e:
                logger.warning(f"tasks表不存在，尝试初始化数据库: {e}")
                from .connection import init_db
                init_db()
                conn = get_db_connection()
            
            conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            
            logger.info(f"任务已删除: task_id={task_id}")
            return True
        except Exception as e:
            logger.error(f"删除任务失败: task_id={task_id}, error={e}")
            return False


class DataPoolBusiness:
    """资产池业务逻辑类
    
    用于操作data_pools和data_pool_assets表，提供资产池的CRUD操作方法
    """
    
    @staticmethod
    def get_all(type: Optional[str] = None) -> Dict[str, Any]:
        """获取所有资产池
        
        Args:
            type: 资产池类型过滤（stock/crypto）
            
        Returns:
            Dict[str, Any]: 所有资产池的字典，键为资产池ID，值为资产池详情
        """
        db: Session = SessionLocal()
        try:
            query = db.query(DataPool)
            if type:
                query = query.filter_by(type=type)
            
            pools = query.order_by(DataPool.name).all()
            
            result = {}
            for pool in pools:
                # 获取资产池包含的资产数量
                asset_count = db.query(DataPoolAsset).filter_by(pool_id=pool.id).count()
                
                result[pool.id] = {
                    "id": pool.id,
                    "name": pool.name,
                    "type": pool.type,
                    "description": pool.description,
                    "color": pool.color,
                    "tags": pool.tags,
                    "asset_count": asset_count,
                    "created_at": pool.created_at,
                    "updated_at": pool.updated_at
                }
            
            return result
        except Exception as e:
            logger.error(f"获取所有资产池失败: error={e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def get(pool_id: int) -> Optional[Dict[str, Any]]:
        """获取指定ID的资产池
        
        Args:
            pool_id: 资产池ID
            
        Returns:
            Optional[Dict[str, Any]]: 资产池详情，如果不存在则返回None
        """
        db: Session = SessionLocal()
        try:
            pool = db.query(DataPool).filter_by(id=pool_id).first()
            if not pool:
                return None
            
            # 获取资产池包含的资产
            assets = db.query(DataPoolAsset).filter_by(pool_id=pool.id).all()
            asset_list = [asset.asset_id for asset in assets]
            
            return {
                "id": pool.id,
                "name": pool.name,
                "type": pool.type,
                "description": pool.description,
                "color": pool.color,
                "tags": pool.tags,
                "assets": asset_list,
                "created_at": pool.created_at,
                "updated_at": pool.updated_at
            }
        except Exception as e:
            logger.error(f"获取资产池失败: pool_id={pool_id}, error={e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def create(name: str, type: str, description: Optional[str] = None, color: Optional[str] = None, tags: Optional[str] = None) -> Optional[int]:
        """创建新资产池
        
        Args:
            name: 资产池名称
            type: 资产池类型（stock/crypto）
            description: 资产池描述
            color: 卡片颜色
            tags: 标签，JSON格式
            
        Returns:
            Optional[int]: 创建的资产池ID，如果失败则返回None
        """
        db: Session = SessionLocal()
        try:
            # 检查资产池名称是否已存在
            existing_pool = db.query(DataPool).filter_by(name=name).first()
            if existing_pool:
                logger.error(f"资产池名称已存在: name={name}")
                return None
            
            # 创建新资产池
            pool = DataPool(
                name=name,
                type=type,
                description=description,
                color=color or "#409EFF",
                tags=tags
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
    def update(pool_id: int, name: Optional[str] = None, description: Optional[str] = None, color: Optional[str] = None, tags: Optional[str] = None) -> bool:
        """更新资产池
        
        Args:
            pool_id: 资产池ID
            name: 资产池名称
            description: 资产池描述
            color: 卡片颜色
            tags: 标签，JSON格式
            
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        db: Session = SessionLocal()
        try:
            pool = db.query(DataPool).filter_by(id=pool_id).first()
            if not pool:
                logger.error(f"资产池不存在: pool_id={pool_id}")
                return False
            
            # 更新资产池信息
            if name:
                pool.name = name
            if description is not None:
                pool.description = description
            if color:
                pool.color = color
            if tags is not None:
                pool.tags = tags
            
            db.commit()
            logger.info(f"资产池已更新: pool_id={pool_id}")
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
        """批量向资产池添加资产
        
        Args:
            pool_id: 资产池ID
            assets: 资产列表（股票代码或加密货币对）
            asset_type: 资产类型（stock/crypto）
            
        Returns:
            bool: 批量添加成功返回True，失败返回False
        """
        db: Session = SessionLocal()
        try:
            # 检查资产池是否存在
            pool = db.query(DataPool).filter_by(id=pool_id).first()
            if not pool:
                logger.error(f"资产池不存在: pool_id={pool_id}")
                return False
            
            # 批量添加资产
            for asset_id in assets:
                # 检查资产是否已存在于资产池中
                existing_asset = db.query(DataPoolAsset).filter_by(pool_id=pool_id, asset_id=asset_id).first()
                if not existing_asset:
                    pool_asset = DataPoolAsset(
                        pool_id=pool_id,
                        asset_id=asset_id,
                        asset_type=asset_type
                    )
                    db.add(pool_asset)
            
            db.commit()
            logger.info(f"批量添加资产到资产池成功: pool_id={pool_id}, asset_count={len(assets)}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"批量添加资产到资产池失败: pool_id={pool_id}, error={e}")
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
    def get_assets(pool_id: int) -> list:
        """获取资产池包含的资产列表
        
        Args:
            pool_id: 资产池ID
            
        Returns:
            list: 资产列表（股票代码或加密货币对）
        """
        db: Session = SessionLocal()
        try:
            assets = db.query(DataPoolAsset).filter_by(pool_id=pool_id).all()
            return [asset.asset_id for asset in assets]
        except Exception as e:
            logger.error(f"获取资产池资产列表失败: pool_id={pool_id}, error={e}")
            return []
        finally:
            db.close()
