#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加密货币对同步脚本

用于从指定交易所同步加密货币对列表到数据库
支持命令行执行，实现松耦合设计
"""

import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

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
        import json
        import time

        from collector.db.database import SessionLocal, init_database_config, engine
        from collector.db.models import CryptoSymbol

        # 初始化数据库配置
        init_database_config()
        
        # 添加字段的简单迁移逻辑
        from sqlalchemy import text
        with engine.begin() as conn:
            # 检查is_deleted字段是否存在
            result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'crypto_symbols' AND column_name = 'is_deleted'
            """))
            
            if not result.fetchone():
                # 添加is_deleted字段
                conn.execute(text("""
                ALTER TABLE crypto_symbols 
                ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE
                """))
                logger.info("已添加is_deleted字段到crypto_symbols表")
            else:
                logger.info("is_deleted字段已存在")
        
        # 重试机制
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"开始数据库操作，重试次数: {retry_count + 1}/{max_retries}")
                db = SessionLocal()
                try:
                    # 开始事务
                    logger.info(f"开始处理{exchange}的货币对数据...")
                    
                    # 1. 获取当前交易所的所有货币对
                    logger.info(f"获取{exchange}的现有货币对数据...")
                    existing_symbols = db.query(CryptoSymbol).filter_by(exchange=exchange).all()
                    existing_symbol_map = {sym.symbol: sym for sym in existing_symbols}
                    logger.info(f"已获取{exchange}的{len(existing_symbol_map)}条现有货币对数据")
                    
                    # 2. 提取新获取的货币对符号
                    new_symbol_map = {sym['symbol']: sym for sym in valid_symbols}
                    
                    # 3. 标记不再存在的货币对为已删除
                    logger.info(f"标记不再存在的{exchange}货币对...")
                    deleted_count = 0
                    for symbol, existing_sym in existing_symbol_map.items():
                        if symbol not in new_symbol_map:
                            existing_sym.is_deleted = True
                            existing_sym.active = False
                            deleted_count += 1
                    if deleted_count > 0:
                        logger.info(f"已标记{deleted_count}条{exchange}货币对为已删除")
                    
                    # 4. 更新现有货币对和插入新货币对
                    logger.info(f"更新和插入{exchange}货币对数据...")
                    updated_count = 0
                    inserted_count = 0
                    
                    for symbol, symbol_info in new_symbol_map.items():
                        # 将JSON对象转换为字符串
                        precision_str = json.dumps(symbol_info['precision'])
                        limits_str = json.dumps(symbol_info['limits'])
                        
                        if symbol in existing_symbol_map:
                            # 更新现有货币对
                            existing_sym = existing_symbol_map[symbol]
                            existing_sym.active = symbol_info['active']
                            existing_sym.is_deleted = False  # 如果之前被标记为删除，现在恢复
                            existing_sym.precision = precision_str
                            existing_sym.limits = limits_str
                            existing_sym.type = symbol_info['type']
                            updated_count += 1
                        else:
                            # 插入新货币对
                            new_symbol = CryptoSymbol(
                                symbol=symbol_info['symbol'],
                                base=symbol_info['base'],
                                quote=symbol_info['quote'],
                                exchange=symbol_info['exchange'],
                                active=symbol_info['active'],
                                precision=precision_str,
                                limits=limits_str,
                                type=symbol_info['type'],
                                is_deleted=False
                            )
                            db.add(new_symbol)
                            inserted_count += 1
                    
                    # 提交事务
                    db.commit()
                    logger.info(f"成功处理{exchange}货币对数据: 更新{updated_count}条，插入{inserted_count}条，标记删除{deleted_count}条")
                    
                    return {
                        'success': True,
                        'message': f"成功同步{len(valid_symbols)}个{exchange}货币对到数据库",
                        'exchange': exchange,
                        'symbol_count': len(valid_symbols),
                        'updated_count': updated_count,
                        'inserted_count': inserted_count,
                        'deleted_count': deleted_count,
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