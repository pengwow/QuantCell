"""数据库CRUD操作

包含所有数据库操作的函数，使用SQLAlchemy ORM进行数据库交互
"""

import json
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

# 导入SQLAlchemy模型和Pydantic模型
from . import models, schemas

# 系统配置CRUD操作

def get_system_config(db: Session, config_key: str) -> Optional[models.SystemConfig]:
    """获取单个系统配置
    
    Args:
        db: 数据库会话
        config_key: 配置键名
        
    Returns:
        Optional[models.SystemConfig]: 系统配置模型实例，不存在则返回None
    """
    return db.query(models.SystemConfig).filter(models.SystemConfig.key == config_key).first()


def get_system_configs(
    db: Session, 
    skip: int = 0, 
    limit: int = 100
) -> List[models.SystemConfig]:
    """获取系统配置列表
    
    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的最大记录数
        
    Returns:
        List[models.SystemConfig]: 系统配置模型实例列表
    """
    return db.query(models.SystemConfig).offset(skip).limit(limit).all()


def create_system_config(
    db: Session, 
    config: schemas.SystemConfigCreate
) -> models.SystemConfig:
    """创建系统配置
    
    Args:
        db: 数据库会话
        config: 创建系统配置的数据模型
        
    Returns:
        models.SystemConfig: 创建后的系统配置模型实例
    """
    # 将Pydantic模型转换为SQLAlchemy模型
    db_config = models.SystemConfig(**config.model_dump())
    
    # 添加到会话并提交
    db.add(db_config)
    db.commit()
    
    # 刷新会话以获取最新数据（包括自动生成的字段）
    db.refresh(db_config)
    
    return db_config


def update_system_config(
    db: Session, 
    config_key: str, 
    config: schemas.SystemConfigUpdate
) -> Optional[models.SystemConfig]:
    """更新系统配置
    
    Args:
        db: 数据库会话
        config_key: 配置键名
        config: 更新系统配置的数据模型
        
    Returns:
        Optional[models.SystemConfig]: 更新后的系统配置模型实例，不存在则返回None
    """
    # 获取要更新的配置
    db_config = get_system_config(db, config_key)
    
    if db_config:
        # 使用exclude_unset=True只更新提供的字段
        update_data = config.model_dump(exclude_unset=True)
        
        # 更新字段
        for field, value in update_data.items():
            setattr(db_config, field, value)
        
        # 提交更新
        db.commit()
        
        # 刷新会话以获取最新数据
        db.refresh(db_config)
    
    return db_config


# 任务CRUD操作

def get_task(db: Session, task_id: str) -> Optional[models.Task]:
    """获取单个任务
    
    Args:
        db: 数据库会话
        task_id: 任务ID
        
    Returns:
        Optional[models.Task]: 任务模型实例，不存在则返回None
    """
    return db.query(models.Task).filter(models.Task.task_id == task_id).first()


def get_tasks(
    db: Session, 
    skip: int = 0, 
    limit: int = 100
) -> List[models.Task]:
    """获取任务列表
    
    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的最大记录数
        
    Returns:
        List[models.Task]: 任务模型实例列表
    """
    return db.query(models.Task).offset(skip).limit(limit).all()


def get_tasks_paginated(
    db: Session, 
    skip: int = 0, 
    limit: int = 10, 
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc"
) -> Tuple[List[models.Task], int]:
    """获取分页任务列表
    
    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的最大记录数
        task_type: 任务类型过滤
        status: 任务状态过滤
        start_time: 开始时间过滤
        end_time: 结束时间过滤
        created_at: 创建时间过滤
        updated_at: 更新时间过滤
        sort_by: 排序字段
        sort_order: 排序顺序（asc或desc）
        
    Returns:
        Tuple[List[models.Task], int]: 任务模型实例列表和总记录数
    """
    from sqlalchemy import asc, desc

    # 构建查询
    query = db.query(models.Task)
    
    # 应用过滤条件
    if task_type:
        query = query.filter(models.Task.task_type == task_type)
    if status:
        query = query.filter(models.Task.status == status)
    if start_time:
        query = query.filter(models.Task.start_time >= start_time)
    if end_time:
        query = query.filter(models.Task.end_time <= end_time)
    if created_at:
        query = query.filter(models.Task.created_at >= created_at)
    if updated_at:
        query = query.filter(models.Task.updated_at <= updated_at)
    
    # 应用排序
    # 验证排序字段是否存在于模型中
    valid_sort_fields = [column.name for column in models.Task.__table__.columns]
    if sort_by not in valid_sort_fields:
        sort_by = "created_at"  # 默认排序字段
    
    # 验证排序顺序
    order_func = desc if sort_order == "desc" else asc
    query = query.order_by(order_func(getattr(models.Task, sort_by)))
    
    # 获取总记录数
    total = query.count()
    
    # 应用分页
    tasks = query.offset(skip).limit(limit).all()
    
    return tasks, total


def create_task(
    db: Session, 
    task: schemas.TaskCreate
) -> models.Task:
    """创建任务
    
    Args:
        db: 数据库会话
        task: 创建任务的数据模型
        
    Returns:
        models.Task: 创建后的任务模型实例
    """
    # 将params字典转换为JSON字符串
    task_dict = task.model_dump()
    task_dict["params"] = json.dumps(task_dict["params"])
    
    # 创建SQLAlchemy模型实例
    db_task = models.Task(**task_dict)
    
    # 添加到会话并提交
    db.add(db_task)
    db.commit()
    
    # 刷新会话以获取最新数据
    db.refresh(db_task)
    
    return db_task


def update_task(
    db: Session, 
    task_id: str, 
    task: schemas.TaskUpdate
) -> Optional[models.Task]:
    """更新任务
    
    Args:
        db: 数据库会话
        task_id: 任务ID
        task: 更新任务的数据模型
        
    Returns:
        Optional[models.Task]: 更新后的任务模型实例，不存在则返回None
    """
    # 获取要更新的任务
    db_task = get_task(db, task_id)
    
    if db_task:
        # 获取更新数据，只更新提供的字段
        update_data = task.model_dump(exclude_unset=True)
        
        # 处理进度字段
        if "progress" in update_data:
            progress = update_data.pop("progress")
            db_task.total = progress.total
            db_task.completed = progress.completed
            db_task.failed = progress.failed
            db_task.current = progress.current
            db_task.percentage = progress.percentage
        
        # 更新其他字段
        for field, value in update_data.items():
            setattr(db_task, field, value)
        
        # 提交更新
        db.commit()
        
        # 刷新会话以获取最新数据
        db.refresh(db_task)
    
    return db_task


def delete_task(db: Session, task_id: str) -> bool:
    """删除任务
    
    Args:
        db: 数据库会话
        task_id: 任务ID
        
    Returns:
        bool: 删除成功返回True，失败返回False
    """
    # 获取要删除的任务
    db_task = get_task(db, task_id)
    
    if db_task:
        # 从会话中删除
        db.delete(db_task)
        db.commit()
        return True
    
    return False


# 特征CRUD操作

def get_feature(
    db: Session, 
    feature_id: int
) -> Optional[models.Feature]:
    """获取单个特征
    
    Args:
        db: 数据库会话
        feature_id: 特征ID
        
    Returns:
        Optional[models.Feature]: 特征模型实例，不存在则返回None
    """
    return db.query(models.Feature).filter(models.Feature.id == feature_id).first()


def get_features(
    db: Session, 
    skip: int = 0, 
    limit: int = 100
) -> List[models.Feature]:
    """获取特征列表
    
    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的最大记录数
        
    Returns:
        List[models.Feature]: 特征模型实例列表
    """
    return db.query(models.Feature).offset(skip).limit(limit).all()


def get_features_by_symbol(
    db: Session, 
    symbol: str
) -> List[models.Feature]:
    """根据货币名称获取特征列表
    
    Args:
        db: 数据库会话
        symbol: 货币名称
        
    Returns:
        List[models.Feature]: 特征模型实例列表
    """
    return db.query(models.Feature).filter(models.Feature.symbol == symbol).all()


def create_feature(
    db: Session, 
    feature: schemas.FeatureCreate
) -> models.Feature:
    """创建特征
    
    Args:
        db: 数据库会话
        feature: 创建特征的数据模型
        
    Returns:
        models.Feature: 创建后的特征模型实例
    """
    # 将Pydantic模型转换为SQLAlchemy模型
    db_feature = models.Feature(**feature.model_dump())
    
    # 添加到会话并提交
    db.add(db_feature)
    db.commit()
    
    # 刷新会话以获取最新数据（包括自动生成的字段）
    db.refresh(db_feature)
    
    return db_feature


def create_features(
    db: Session, 
    features: List[schemas.FeatureCreate]
) -> List[models.Feature]:
    """批量创建特征
    
    Args:
        db: 数据库会话
        features: 创建特征的数据模型列表
        
    Returns:
        List[models.Feature]: 创建后的特征模型实例列表
    """
    # 使用原始SQL插入，避免SQLAlchemy批量插入时的排序问题
    created_features = []
    
    from sqlalchemy import text

    # 准备插入语句
    insert_sql = text("""
    INSERT INTO features (symbol, feature_name, freq)
    VALUES (:symbol, :feature_name, :freq)
    RETURNING id, created_at, updated_at
    """)
    
    for feature in features:
        # 准备插入数据
        insert_data = {
            "symbol": feature.symbol,
            "feature_name": feature.feature_name,
            "freq": feature.freq
        }
        
        # 执行原始SQL插入，获取自动生成的字段值
        result = db.execute(insert_sql, insert_data)
        
        # 获取插入结果
        insert_result = result.fetchone()
        if insert_result:
            # 创建Feature实例，不需要添加到会话中，因为数据已经插入到数据库中
            db_feature = models.Feature(
                id=insert_result[0],
                symbol=feature.symbol,
                feature_name=feature.feature_name,
                freq=feature.freq,
                created_at=insert_result[1],
                updated_at=insert_result[2]
            )
            created_features.append(db_feature)
    
    # 提交事务，确保所有操作都已完成
    db.commit()
    
    return created_features


def update_feature(
    db: Session, 
    feature_id: int, 
    feature: schemas.FeatureUpdate
) -> Optional[models.Feature]:
    """更新特征
    
    Args:
        db: 数据库会话
        feature_id: 特征ID
        feature: 更新特征的数据模型
        
    Returns:
        Optional[models.Feature]: 更新后的特征模型实例，不存在则返回None
    """
    # 获取要更新的特征
    db_feature = get_feature(db, feature_id)
    
    if db_feature:
        # 使用exclude_unset=True只更新提供的字段
        update_data = feature.model_dump(exclude_unset=True)
        
        # 更新字段
        for field, value in update_data.items():
            setattr(db_feature, field, value)
        
        # 提交更新
        db.commit()
        
        # 刷新会话以获取最新数据
        db.refresh(db_feature)
    
    return db_feature


def delete_feature(
    db: Session, 
    feature_id: int
) -> bool:
    """删除特征
    
    Args:
        db: 数据库会话
        feature_id: 特征ID
        
    Returns:
        bool: 删除成功返回True，失败返回False
    """
    # 获取要删除的特征
    db_feature = get_feature(db, feature_id)
    
    if db_feature:
        # 从会话中删除
        db.delete(db_feature)
        db.commit()
        return True
    
    return False


def delete_features_by_symbol(
    db: Session, 
    symbol: str
) -> bool:
    """根据货币名称删除特征
    
    Args:
        db: 数据库会话
        symbol: 货币名称
        
    Returns:
        bool: 删除成功返回True，失败返回False
    """
    # 删除所有匹配的特征
    result = db.query(models.Feature).filter(models.Feature.symbol == symbol).delete()
    db.commit()
    
    return result > 0
