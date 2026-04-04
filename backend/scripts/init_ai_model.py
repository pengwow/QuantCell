#!/usr/bin/env python3
"""
初始化 AI 模型模块数据库和默认配置

用法:
    cd backend && uv run python scripts/init_ai_model.py
"""

import os
import sys
import json
import uuid
from pathlib import Path
from datetime import datetime

# 添加 backend 到路径
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, Column, String, Text, Boolean, DateTime, Index, func
from sqlalchemy.orm import declarative_base, sessionmaker
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)

# 创建独立的 Base
Base = declarative_base()


class ThinkingChain(Base):
    """思维链模型"""
    __tablename__ = "thinking_chains"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    chain_type = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    steps = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    __table_args__ = (
        Index('idx_thinking_chain_type_active', 'chain_type', 'is_active'),
        Index('idx_thinking_chain_type_created', 'chain_type', 'created_at'),
    )


class AIProvider(Base):
    """AI 提供商模型"""
    __tablename__ = "ai_providers"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String(100), nullable=False)
    provider_type = Column(String(50), nullable=False, index=True)
    api_key = Column(Text, nullable=True)
    api_base = Column(String(500), nullable=True)
    model = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    is_default = Column(Boolean, default=False, index=True)
    config = Column(Text, nullable=True)  # JSON 格式存储额外配置
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    __table_args__ = (
        Index('idx_ai_provider_type_active', 'provider_type', 'is_active'),
        Index('idx_ai_provider_default', 'is_default'),
    )


def init_database():
    """初始化数据库表"""
    try:
        # 获取数据库路径
        db_path = os.path.join(backend_path, "data", "quantcell_sqlite.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 创建引擎
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False}
        )
        
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        
        logger.info(f"数据库表创建成功: {db_path}")
        return engine
        
    except Exception as e:
        logger.error(f"数据库表创建失败: {e}")
        return None


def init_default_thinking_chain(engine):
    """初始化默认思维链配置"""
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # 检查是否已存在
        existing = db.query(ThinkingChain).filter(
            ThinkingChain.chain_type == "strategy_generation",
            ThinkingChain.is_active == True
        ).first()
        
        if existing:
            logger.info("默认策略生成思维链已存在，跳过创建")
            db.close()
            return True
        
        # 创建默认思维链
        default_chain = ThinkingChain(
            id=str(uuid.uuid4()),
            chain_type="strategy_generation",
            name="默认策略生成思维链",
            description="用于生成交易策略的默认思维链",
            steps=json.dumps([
                {
                    "step": 1,
                    "name": "需求分析",
                    "description": "分析用户的策略需求，理解交易目标和约束条件"
                },
                {
                    "step": 2,
                    "name": "策略设计",
                    "description": "设计策略的整体架构，包括入场条件、出场条件和风险管理"
                },
                {
                    "step": 3,
                    "name": "代码生成",
                    "description": "根据设计生成可执行的策略代码"
                },
                {
                    "step": 4,
                    "name": "代码审查",
                    "description": "审查生成的代码，确保语法正确和逻辑合理"
                }
            ], ensure_ascii=False),
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.add(default_chain)
        db.commit()
        db.close()
        
        logger.info("默认策略生成思维链创建成功")
        return True
        
    except Exception as e:
        logger.error(f"初始化默认思维链失败: {e}")
        return False


def init_default_ai_provider(engine):
    """初始化默认 AI 提供商配置"""
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # 检查是否已存在
        existing = db.query(AIProvider).filter(
            AIProvider.is_default == True
        ).first()
        
        if existing:
            logger.info("默认 AI 提供商已存在，跳过创建")
            db.close()
            return True
        
        # 创建默认 OpenAI 提供商配置
        default_provider = AIProvider(
            id=str(uuid.uuid4()),
            name="OpenAI",
            provider_type="openai",
            api_key="",
            api_base="https://api.openai.com/v1",
            model="gpt-4",
            is_active=True,
            is_default=True,
            config=json.dumps({
                "temperature": 0.7,
                "max_tokens": 4096
            }, ensure_ascii=False),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.add(default_provider)
        db.commit()
        db.close()
        
        logger.info("默认 AI 提供商配置创建成功")
        return True
        
    except Exception as e:
        logger.error(f"初始化默认 AI 提供商失败: {e}")
        return False


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始初始化 AI 模型模块")
    logger.info("=" * 60)
    
    # 1. 初始化数据库表
    logger.info("\n[1/3] 初始化数据库表...")
    engine = init_database()
    if not engine:
        logger.error("数据库初始化失败，退出")
        sys.exit(1)
    
    # 2. 初始化默认思维链
    logger.info("\n[2/3] 初始化默认思维链...")
    init_default_thinking_chain(engine)
    
    # 3. 初始化默认 AI 提供商
    logger.info("\n[3/3] 初始化默认 AI 提供商...")
    init_default_ai_provider(engine)
    
    logger.info("\n" + "=" * 60)
    logger.info("AI 模型模块初始化完成")
    logger.info("=" * 60)
    logger.info("\n提示:")
    logger.info("1. 数据库表已创建 (thinking_chains, ai_providers)")
    logger.info("2. 默认思维链已创建")
    logger.info("3. 默认 AI 提供商已创建（需要配置 API Key）")
    logger.info("4. 请在系统设置中配置 OpenAI API Key")


if __name__ == "__main__":
    main()
