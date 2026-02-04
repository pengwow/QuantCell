# -*- coding: utf-8 -*-
"""
加密货币对同步服务

用于从指定交易所同步加密货币对列表到数据库
作为业务模块提供服务
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from loguru import logger

from collector.db.database import SessionLocal, init_database_config
from collector.db.models import CryptoSymbol


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
    # 日志级别由loguru自动管理，无需手动设置

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
            parsed_url = urlparse(proxy_url)

            if parsed_url.scheme in ['socks5', 'socks4', 'socks4a']:
                # SOCKS代理使用proxy属性
                exchange_instance.proxy = proxy_url
            else:
                # HTTP/HTTPS代理使用proxies字典
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
                parsed_url = urlparse(env_proxy)

                if parsed_url.scheme in ['socks5', 'socks4', 'socks4a']:
                    # SOCKS代理使用proxy属性
                    exchange_instance.proxy = env_proxy
                else:
                    # HTTP/HTTPS代理使用proxies字典
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

        # 初始化数据库配置
        init_database_config()

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


class CryptoSymbolService:
    """加密货币对同步服务类

    提供加密货币对同步相关的业务逻辑
    """

    @staticmethod
    def sync_symbols(
        exchange: str = 'binance',
        proxy_enabled: bool = False,
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """同步指定交易所的加密货币对

        Args:
            exchange: 交易所名称
            proxy_enabled: 是否启用代理
            proxy_url: 代理地址
            proxy_username: 代理用户名
            proxy_password: 代理密码

        Returns:
            Dict[str, Any]: 同步结果
        """
        return sync_crypto_symbols(
            exchange=exchange,
            proxy_enabled=proxy_enabled,
            proxy_url=proxy_url,
            proxy_username=proxy_username,
            proxy_password=proxy_password,
        )

    @staticmethod
    def sync_all_exchanges(
        exchanges: list = None,
        proxy_enabled: bool = False,
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """同步多个交易所的加密货币对

        Args:
            exchanges: 交易所列表，默认为['binance']
            proxy_enabled: 是否启用代理
            proxy_url: 代理地址
            proxy_username: 代理用户名
            proxy_password: 代理密码

        Returns:
            Dict[str, Any]: 各交易所同步结果汇总
        """
        if exchanges is None:
            exchanges = ['binance']

        results = {}
        for exchange in exchanges:
            logger.info(f"开始同步{exchange}交易所的货币对")
            result = sync_crypto_symbols(
                exchange=exchange,
                proxy_enabled=proxy_enabled,
                proxy_url=proxy_url,
                proxy_username=proxy_username,
                proxy_password=proxy_password,
            )
            results[exchange] = result

        return {
            'success': all(r.get('success', False) for r in results.values()),
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
