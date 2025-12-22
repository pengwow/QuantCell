#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加密货币对同步脚本

用于从指定交易所同步加密货币对列表到数据库
支持命令行执行，实现松耦合设计
"""

import logging
import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime
import fire

# 添加项目根目录到Python路径
# 获取当前脚本所在目录的父目录（即backend目录）
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
# 将backend目录添加到Python路径
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('sync_crypto_symbols')


def sync_crypto_symbols(
    exchange: str = 'binance',
    proxy_enabled: bool = False,
    proxy_url: Optional[str] = None,
    proxy_username: Optional[str] = None,
    proxy_password: Optional[str] = None,
    log_level: str = 'info'
) -> Dict[str, Any]:
    """
    同步加密货币对到数据库
    
    Args:
        exchange: 交易所名称，如binance、okx等
        proxy_enabled: 是否启用代理
        proxy_url: 代理地址
        proxy_username: 代理用户名
        proxy_password: 代理密码
        log_level: 日志级别，可选值：debug, info, warning, error, critical
    
    Returns:
        Dict[str, Any]: 同步结果信息
    """
    # 设置日志级别
    logger.setLevel(getattr(logging, log_level.upper()))
    
    try:
        logger.info(f"开始同步加密货币对，交易所: {exchange}")
        
        # 动态导入CCXT库
        import ccxt
        
        # 1. 先从交易所获取数据，避免数据库锁导致无法获取市场数据
        logger.info(f"从{exchange}获取市场数据...")
        
        # 创建交易所实例
        exchange_instance = getattr(ccxt, exchange)()
        exchange_instance.timeout = 30000  # 增加超时时间到30秒
        exchange_instance.enableRateLimit = True  # 启用速率限制
        
        # 配置代理
        if proxy_enabled and proxy_url:
            logger.info(f"启用代理: {proxy_url}")
            # ccxt库的代理配置应该使用proxies属性（字典格式）
            exchange_instance.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            if proxy_username and proxy_password:
                exchange_instance.proxy_auth = (proxy_username, proxy_password)
        else:
            # 尝试使用环境变量中的代理配置
            env_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')
            if env_proxy:
                logger.info(f"使用环境变量中的代理: {env_proxy}")
                exchange_instance.proxies = {
                    'http': env_proxy,
                    'https': env_proxy
                }
        
        # 获取市场数据
        markets = exchange_instance.load_markets()
        
        # 过滤有效的货币对
        valid_symbols = []
        for symbol, market in markets.items():
            if market.get('active', True):
                symbol_info = {
                    'symbol': symbol,
                    'base': market.get('base'),
                    'quote': market.get('quote'),
                    'exchange': exchange,
                    'active': market.get('active'),
                    'precision': market.get('precision', {}),
                    'limits': market.get('limits', {}),
                    'type': market.get('type')
                }
                valid_symbols.append(symbol_info)
        
        logger.info(f"获取到{len(valid_symbols)}个有效的{exchange}货币对")
        
        # 2. 处理数据库操作
        logger.info(f"开始保存{exchange}货币对到数据库...")
        
        # 动态导入数据库相关模块
        from collector.db.database import init_database_config, SessionLocal
        import collector.db.models as models
        import json
        import time
        
        # 初始化数据库配置
        init_database_config()
        
        # 重新导入Base、engine和db_type，确保它们已经被初始化
        from collector.db.database import Base, engine, db_type
        from collector.db.models import CryptoSymbol
        
        # 表迁移逻辑：先删除旧表再创建新表，确保表结构正确
        logger.info("开始表迁移...")
        
        try:
            # 使用原始SQL语句创建表，完全控制生成的SQL
            from sqlalchemy import text
            with engine.begin() as conn:
                # 先删除旧表
                conn.execute(text("DROP TABLE IF EXISTS crypto_symbols CASCADE"))
                logger.info("旧表删除成功")
                
                # 创建序列用于id自增
                conn.execute(text("DROP SEQUENCE IF EXISTS crypto_symbols_id_seq CASCADE"))
                conn.execute(text("CREATE SEQUENCE crypto_symbols_id_seq START 1"))
                logger.info("序列创建成功")
                
                # 创建新表，使用序列的nextval作为id的默认值
                conn.execute(text("""
                CREATE TABLE crypto_symbols (
                    id INTEGER PRIMARY KEY DEFAULT nextval('crypto_symbols_id_seq'),
                    symbol VARCHAR NOT NULL,
                    base VARCHAR NOT NULL,
                    quote VARCHAR NOT NULL,
                    exchange VARCHAR NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    precision TEXT,
                    limits TEXT,
                    type VARCHAR,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    CONSTRAINT unique_symbol_exchange UNIQUE (symbol, exchange)
                )
                """))
                logger.info("数据库表创建成功")
        except Exception as e:
            logger.error(f"表迁移失败: {e}")
            raise
        
        # 重试机制
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"开始数据库操作，重试次数: {retry_count + 1}/{max_retries}")
                db = SessionLocal()
                try:
                    # 先删除该交易所的旧数据
                    logger.info(f"开始删除{exchange}的旧货币对数据...")
                    from sqlalchemy import text
                    result = db.execute(text("DELETE FROM crypto_symbols WHERE exchange = :exchange"), {'exchange': exchange})
                    deleted_count = result.rowcount
                    logger.info(f"已删除{exchange}的{deleted_count}条旧货币对数据")
                    
                    # 批量插入新数据
                    logger.info(f"开始批量插入{exchange}的{len(valid_symbols)}条货币对数据...")
                    
                    # 使用原始SQL批量插入，不包含id字段
                    insert_stmt = text("""
                    INSERT INTO crypto_symbols (symbol, base, quote, exchange, active, precision, limits, type)
                    VALUES (:symbol, :base, :quote, :exchange, :active, :precision, :limits, :type)
                    """)
                    
                    for i, symbol_info in enumerate(valid_symbols):
                        # 每处理100条记录记录一次日志
                        if i % 100 == 0:
                            logger.debug(f"已处理{exchange}的{i}/{len(valid_symbols)}条货币对数据")
                        
                        # 将JSON对象转换为字符串
                        precision_str = json.dumps(symbol_info['precision'])
                        limits_str = json.dumps(symbol_info['limits'])
                        
                        # 执行单条插入
                        db.execute(insert_stmt, {
                            'symbol': symbol_info['symbol'],
                            'base': symbol_info['base'],
                            'quote': symbol_info['quote'],
                            'exchange': symbol_info['exchange'],
                            'active': symbol_info['active'],
                            'precision': precision_str,
                            'limits': limits_str,
                            'type': symbol_info['type']
                        })
                    
                    db.commit()
                    logger.info(f"成功将{len(valid_symbols)}个{exchange}货币对保存到数据库")
                    
                    return {
                        'success': True,
                        'message': f"成功同步{len(valid_symbols)}个{exchange}货币对到数据库",
                        'exchange': exchange,
                        'symbol_count': len(valid_symbols),
                        'timestamp': datetime.now().isoformat()
                    }
                finally:
                    logger.debug("关闭数据库连接...")
                    db.close()
                    logger.debug("数据库连接已关闭")
                
            except Exception as e:
                retry_count += 1
                error_msg = f"数据库操作失败: {e}"
                logger.error(error_msg)
                
                # 检查是否是锁冲突
                if "lock" in str(e).lower() and retry_count < max_retries:
                    wait_time = retry_count * 2  # 指数退避
                    logger.warning(f"数据库锁冲突，{wait_time}秒后重试... ({retry_count}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"保存货币对到数据库失败，重试次数已用完: {e}")
                    raise
        
    except Exception as e:
        logger.error(f"同步加密货币对失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'message': f"同步失败: {str(e)}",
            'exchange': exchange,
            'timestamp': datetime.now().isoformat()
        }


def main():
    """
    主函数，使用fire处理命令行参数
    """
    # 使用fire调用sync_crypto_symbols函数
    result = fire.Fire(sync_crypto_symbols)
    
    # 输出结果
    if result['success']:
        logger.info(f"同步完成: {result['message']}")
        sys.exit(0)
    else:
        logger.error(f"同步失败: {result['message']}")
        sys.exit(1)


if __name__ == '__main__':
    main()