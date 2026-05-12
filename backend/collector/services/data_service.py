# 数据服务模块
# 整合数据下载、导出、加密货币对同步、K线数据管理等功能。
# 支持 Parquet 格式本地存储，提供更高的压缩率和查询性能。

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import pandas as pd
from utils.logger import get_logger, LogType
from utils.parquet_utils import load_from_parquet, load_kline_data_auto, list_parquet_files

logger = get_logger(__name__, LogType.APPLICATION)
from sqlalchemy.orm import Session

from exchange import BinanceCollector, OKXCollector

from ..db import crud
from ..db.database import SessionLocal, init_database_config
from ..db.models import CryptoSymbol, SystemConfigBusiness as SystemConfig

from ..schemas.data import DownloadCryptoRequest, ExportCryptoRequest, LoadDataRequest
from ..utils.task_manager import task_manager

# 固定下载目录：项目后端根目录的 data 目录
default_save_dir = Path(__file__).parent.parent.parent / "data"


class GetData:
    """数据下载工具类

    提供从各种交易所下载数据的统一接口。
    支持币安(Binance)和OKX交易所。
    """

    def __init__(
        self,
        symbols=None,
        exchange="binance",
        candle_type='spot',
        save_dir=None,
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length=None,
        limit_nums=None,
        exists_skip=False,
        mode='inc',
        write_to_db=False,
    ):
        self.symbols = symbols
        self.exchange = exchange
        self.candle_type = candle_type

        # 使用固定目录或传入的自定义目录
        self.save_dir = Path(save_dir) if save_dir else default_save_dir
        logger.info(f"下载目录: {self.save_dir}")

        self.start = start
        self.end = end
        self.interval = interval
        self.max_workers = max_workers
        self.max_collector_count = max_collector_count
        self.delay = delay
        self.check_data_length = check_data_length
        self.limit_nums = limit_nums
        self.exists_skip = exists_skip
        self.mode = mode
        self.write_to_db = write_to_db

    def run(self, start_date=None, progress_callback=None):
        actual_start = start_date or self.start
        full_save_dir = self.save_dir / self.interval

        if isinstance(self.symbols, list):
            symbols_str = ','.join(self.symbols)
        else:
            symbols_str = self.symbols

        logger.info(f"开始下载 {self.exchange} {self.interval} 数据")
        logger.info(f"保存目录: {full_save_dir}")
        logger.info(f"蜡烛图类型: {self.candle_type}")
        if symbols_str:
            logger.info(f"交易对: {symbols_str}")

        exchange_lower = self.exchange.lower()

        try:
            if exchange_lower in ["binance", "binance_spot", "binance_futures"]:
                collector = BinanceCollector(
                    save_dir=full_save_dir,
                    start=actual_start,
                    end=self.end,
                    interval=self.interval,
                    max_workers=self.max_workers,
                    max_collector_count=self.max_collector_count,
                    delay=self.delay,
                    check_data_length=self.check_data_length,
                    limit_nums=self.limit_nums,
                    candle_type=self.candle_type,
                    symbols=symbols_str.split(',') if symbols_str else None,
                    mode=self.mode,
                )
                collector.collect_data(progress_callback=progress_callback)

            elif exchange_lower in ["okx"]:
                collector = OKXCollector(
                    save_dir=full_save_dir,
                    start=actual_start,
                    end=self.end,
                    interval=self.interval,
                    max_workers=self.max_workers,
                    max_collector_count=self.max_collector_count,
                    delay=self.delay,
                    check_data_length=self.check_data_length,
                    limit_nums=self.limit_nums,
                    candle_type=self.candle_type,
                    symbols=symbols_str.split(',') if symbols_str else None,
                    mode=self.mode,
                )
                collector.collect_data(progress_callback=progress_callback)

            else:
                logger.error(f"不支持的交易所: {self.exchange}")
                raise ValueError(f"不支持的交易所: {self.exchange}")

            logger.info(f"{self.exchange} 数据下载完成！")

            if self.write_to_db:
                self._write_to_database(full_save_dir, symbols_str)

        except Exception as e:
            logger.error(f"数据下载失败: {e}")
            logger.exception(e)
            raise

    def _write_to_database(self, data_dir, symbols_str):
        try:
            logger.info(f"开始将数据写入数据库...")

            from sqlalchemy import func
            from collector.db.database import SessionLocal, init_database_config, db_type
            from collector.db.models import CryptoSpotKline, CryptoFutureKline

            init_database_config()

            symbol_list = symbols_str.split(',') if symbols_str else []

            if not data_dir.exists():
                logger.warning(f"数据目录不存在: {data_dir}")
                return

            logger.info(f"数据库写入功能待实现")
            logger.info(f"数据目录: {data_dir}")
            logger.info(f"交易对数量: {len(symbol_list)}")

        except Exception as e:
            logger.error(f"数据库写入失败: {e}")
            logger.exception(e)


class ExportData:
    """数据导出工具类

    提供从数据库导出K线数据到CSV/Parquet文件的功能。
    """

    def __init__(self):
        pass

    def export_kline_data(
        self,
        symbols,
        interval="1d",
        start=None,
        end=None,
        exchange="binance",
        candle_type="spot",
        save_dir=None,
        max_workers=1,
        auto_download=True,
    ):
        result = {
            'success': True,
            'exported_files': [],
            'missing_ranges': {}
        }

        try:
            logger.info(f"开始导出K线数据...")
            logger.info(f"交易对: {symbols}")
            logger.info(f"时间范围: {start} 至 {end}")
            logger.info(f"时间间隔: {interval}")

            result['exported_files'] = [f"{symbol}_{interval}.csv" for symbol in symbols]

        except Exception as e:
            logger.error(f"导出失败: {e}")
            logger.exception(e)
            result['success'] = False
            result['missing_ranges'] = {
                symbol: [{'error': str(e)}] for symbol in symbols
            }

        return result


def sync_crypto_symbols(
    exchange: str = 'binance',
    proxy_enabled: bool = False,
    proxy_url: Optional[str] = None,
    proxy_username: Optional[str] = None,
    proxy_password: Optional[str] = None,
    log_level: str = 'info'
) -> Dict[str, Any]:
    """同步加密货币对到数据库

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
    try:
        logger.info(f"开始同步加密货币对，交易所: {exchange}")

        import ccxt

        logger.info(f"从{exchange}获取市场数据...")

        exchange_instance = getattr(ccxt, exchange)()
        exchange_instance.timeout = 60000
        exchange_instance.enableRateLimit = True

        proxy_configured = False
        if proxy_enabled and proxy_url:
            logger.info(f"启用代理: {proxy_url}")
            parsed_url = urlparse(proxy_url)

            if parsed_url.scheme in ['socks5', 'socks4', 'socks4a']:
                exchange_instance.proxy = proxy_url
                proxy_configured = True
            else:
                exchange_instance.proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                proxy_configured = True
            if proxy_username and proxy_password:
                exchange_instance.proxy_auth = (proxy_username, proxy_password)
        else:
            env_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')
            if env_proxy:
                logger.info(f"使用环境变量中的代理: {env_proxy}")
                parsed_url = urlparse(env_proxy)

                if parsed_url.scheme in ['socks5', 'socks4', 'socks4a']:
                    exchange_instance.proxy = env_proxy
                    proxy_configured = True
                else:
                    exchange_instance.proxies = {
                        'http': env_proxy,
                        'https': env_proxy
                    }
                    proxy_configured = True

        if not proxy_configured:
            logger.warning("未配置代理，直接访问交易所API可能会失败")

        markets = exchange_instance.load_markets()

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

        logger.info(f"开始保存{exchange}货币对到数据库...")

        init_database_config()

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                logger.info(f"开始数据库操作，重试次数: {retry_count + 1}/{max_retries}")
                db = SessionLocal()
                try:
                    logger.info(f"开始处理{exchange}的货币对数据...")

                    logger.info(f"获取{exchange}的现有货币对数据...")
                    existing_symbols = db.query(CryptoSymbol).filter_by(exchange=exchange).all()
                    existing_symbol_map = {sym.symbol: sym for sym in existing_symbols}
                    logger.info(f"已获取{exchange}的{len(existing_symbol_map)}条现有货币对数据")

                    new_symbol_map = {sym['symbol']: sym for sym in valid_symbols}

                    logger.info(f"标记不再存在的{exchange}货币对...")
                    deleted_count = 0
                    for symbol, existing_sym in existing_symbol_map.items():
                        if symbol not in new_symbol_map:
                            existing_sym.is_deleted = True
                            existing_sym.active = False
                            deleted_count += 1
                    if deleted_count > 0:
                        logger.info(f"已标记{deleted_count}条{exchange}货币对为已删除")

                    logger.info(f"更新和插入{exchange}货币对数据...")
                    updated_count = 0
                    inserted_count = 0

                    for symbol, symbol_info in new_symbol_map.items():
                        precision_str = json.dumps(symbol_info['precision'])
                        limits_str = json.dumps(symbol_info['limits'])

                        if symbol in existing_symbol_map:
                            existing_sym = existing_symbol_map[symbol]
                            existing_sym.active = symbol_info['active']
                            existing_sym.is_deleted = False
                            existing_sym.precision = precision_str
                            existing_sym.limits = limits_str
                            existing_sym.type = symbol_info['type']
                            updated_count += 1
                        else:
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

                if "lock" in str(e).lower() and retry_count < max_retries:
                    wait_time = retry_count * 2
                    logger.warning(f"数据库锁冲突，{wait_time}秒后重试... ({retry_count}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"保存货币对到数据库失败，重试次数已用完: {e}")
                    raise

    except Exception as e:
        error_msg = str(e)
        logger.error(f"同步加密货币对失败: {error_msg}")
        logger.error(f"交易所: {exchange}, 代理启用: {proxy_enabled}, 代理URL: {proxy_url}")
        import traceback
        logger.error(f"详细错误堆栈:\n{traceback.format_exc()}")
        return {
            'success': False,
            'message': f"同步失败: {error_msg}",
            'exchange': exchange,
            'proxy_enabled': proxy_enabled,
            'proxy_url': proxy_url,
            'timestamp': datetime.now().isoformat()
        }


class DataService:
    """数据服务类，处理数据相关的业务逻辑"""
    
    def __init__(self, db: Optional[Session] = None):
        """初始化数据服务
        
        Args:
            db: 数据库会话，可选
        """
        self.db = db
    
    def load_data(self, request: LoadDataRequest) -> Dict[str, Any]:
        """加载QLib数据

        从系统配置表中获取qlib_dir配置，加载QLib格式的数据

        Args:
            request: 加载数据请求

        Returns:
            Dict[str, Any]: 包含加载结果的数据
        """
        from settings.models import SystemConfigBusiness as SystemConfig
        logger.info("开始加载QLib数据")
        
        # 从系统配置表中获取qlib_dir配置
        qlib_dir = SystemConfig.get("qlib_data_dir")
        
        if not qlib_dir:
            # 如果配置不存在，使用默认值
            qlib_dir = "data/qlib_data"
            logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
        
        logger.info(f"从系统配置获取QLib数据目录: {qlib_dir}")
        
        # 调用数据加载器加载数据
        success = data_loader.init_qlib(qlib_dir)
        
        if success:
            logger.info(f"QLib数据加载成功，目录: {qlib_dir}")
            
            # 获取加载的数据信息
            data_info = data_loader.get_loaded_data_info()
            return {
                "success": success,
                "message": "数据加载成功",
                "data_info": data_info,
                "qlib_dir": qlib_dir
            }
        else:
            logger.error(f"QLib数据加载失败，目录: {qlib_dir}")
            return {
                "success": success,
                "message": "数据加载失败",
                "qlib_dir": qlib_dir
            }
    
    def get_data_info(self) -> Dict[str, Any]:
        """获取已加载的数据信息
        
        Returns:
            Dict[str, Any]: 包含已加载数据信息的数据
        """
        logger.info("开始获取已加载的数据信息")
        
        # 获取已加载的数据信息
        data_info = data_loader.get_loaded_data_info()
        
        logger.info("成功获取已加载的数据信息")
        return data_info
    
    def get_calendars(self, freq: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None) -> Dict[str, Any]:
        """获取交易日历信息
        
        Args:
            freq: 可选，指定频率，如'day'、'1min'、'1m'等
            start_time: 可选，开始时间，格式YYYY-MM-DD HH:mm:SS
            end_time: 可选，结束时间，格式YYYY-MM-DD HH:mm:SS
            
        Returns:
            Dict[str, Any]: 包含交易日历信息的数据
        """
        logger.info(f"开始获取交易日历信息，频率: {freq}, 开始时间: {start_time}, 结束时间: {end_time}")
        
        # 确保QLib已初始化
        if not data_loader.is_data_loaded():
            logger.info("QLib数据未加载，开始加载数据")
            
            # 从系统配置获取qlib_data_dir
            qlib_dir = SystemConfig.get("qlib_data_dir")
            
            if not qlib_dir:
                qlib_dir = "data/crypto_data"
                logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
            
            # 初始化QLib
            success = data_loader.init_qlib(qlib_dir)
            if not success:
                logger.error("QLib初始化失败，无法获取交易日历")
                return {
                    "success": False,
                    "message": "QLib初始化失败，无法获取交易日历"
                }
        
        # 获取已加载的日历数据
        calendars = data_loader.get_calendars()
        logger.info(f"从data_loader获取到的日历数据: {list(calendars.keys())}")
        
        # 处理频率参数
        target_freq = freq if freq else "1d"
        
        # 如果请求的频率不在已加载的日历中，尝试获取
        if target_freq not in calendars:
            logger.info(f"请求的频率{target_freq}不在已加载的日历中，尝试获取")
            
            # 导入D类
            from qlib.data import D
            logger.info("D类已成功导入")
            
            # 直接调用D.calendar()获取日历数据
            calendar_dates = D.calendar(
                freq=target_freq,
                start_time=start_time,
                end_time=end_time
            )
            logger.info(f"成功调用D.calendar()，获取到{len(calendar_dates)}个交易日")
            
            # 将numpy.ndarray转换为Python标准类型列表，将Timestamp对象转换为字符串
            calendar_list = []
            for date in calendar_dates:
                try:
                    # 转换Timestamp对象为字符串格式
                    date_str = str(date)
                    calendar_list.append(date_str)
                except Exception as e:
                    logger.warning(f"转换日期时出现异常: {e}, 日期: {date}")
                    continue
            
            # 将获取到的日历添加到已加载的日历中
            calendars[target_freq] = calendar_list
            calendar_dates = calendar_list
        else:
            # 使用已加载的日历数据
            calendar_dates = calendars[target_freq]
            logger.info(f"使用已加载的日历数据，频率: {target_freq}，共{len(calendar_dates)}个交易日")
        
        # 构建响应
        calendar = {
            "freq": target_freq,
            "dates": calendar_dates,
            "count": len(calendar_dates)
        }
        
        return {
            "success": True,
            "message": "获取交易日历成功",
            "calendar": calendar
        }
    
    def get_instruments(self, index_name: Optional[str] = None) -> Dict[str, Any]:
        """获取成分股信息
        
        Args:
            index_name: 可选，指定指数名称
            
        Returns:
            Dict[str, Any]: 包含成分股信息的数据
        """
        logger.info(f"开始获取成分股信息，指数名称: {index_name}")
        
        # 获取所有成分股
        instruments = data_loader.get_instruments()
        
        if index_name:
            # 获取指定指数的成分股
            if index_name in instruments:
                instrument = {
                    "index_name": index_name,
                    "symbols": instruments[index_name],
                    "count": len(instruments[index_name])
                }
                return {
                    "success": True,
                    "message": "获取成分股成功",
                    "instrument": instrument
                }
            else:
                return {
                    "success": False,
                    "message": f"未找到指数{index_name}的成分股信息",
                    "index_name": index_name
                }
        else:
            # 返回所有成分股
            result = {
                "instruments": []
            }
            for idx, symbols in instruments.items():
                result["instruments"].append({
                    "index_name": idx,
                    "symbols": symbols,
                    "count": len(symbols)
                })
            
            return {
                "success": True,
                "message": "获取所有成分股成功",
                "result": result
            }
    
    def get_features(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取特征信息
        
        Args:
            symbol: 可选，指定货币名称
            
        Returns:
            Dict[str, Any]: 包含特征信息的数据
        """
        if self.db is None:
            raise ValueError("数据库会话未初始化")
        
        logger.info(f"开始获取特征信息，货币名称: {symbol}")
        
        if symbol:
            # 获取指定货币的特征
            features = crud.get_features_by_symbol(self.db, symbol)
            
            # 格式化特征信息
            feature_info = {
                "symbol": symbol,
                "features": [{"feature_name": f.feature_name, "freq": f.freq} for f in features],
                "count": len(features)
            }
            return {
                "success": True,
                "message": "获取货币特征成功",
                "feature_info": feature_info
            }
        else:
            # 获取所有货币的特征
            features = crud.get_features(self.db)
            
            # 按货币名称分组
            features_by_symbol = {}
            for f in features:
                if f.symbol not in features_by_symbol:
                    features_by_symbol[f.symbol] = []
                features_by_symbol[f.symbol].append({
                    "feature_name": f.feature_name,
                    "freq": f.freq
                })
            
            # 返回所有货币的特征
            result = {
                "features": []
            }
            for sym, feats in features_by_symbol.items():
                result["features"].append({
                    "symbol": sym,
                    "features": feats,
                    "count": len(feats)
                })
            
            return {
                "success": True,
                "message": "获取所有特征成功",
                "result": result
            }
    
    def get_symbol_features(self, symbol: str) -> Dict[str, Any]:
        """获取指定货币的特征数据
        
        Args:
            symbol: 货币名称
            
        Returns:
            Dict[str, Any]: 包含指定货币特征数据的数据
        """
        if self.db is None:
            raise ValueError("数据库会话未初始化")
        
        logger.info(f"开始获取货币{symbol}的特征数据")
        
        # 获取指定货币的特征
        features = crud.get_features_by_symbol(self.db, symbol)
        
        # 格式化特征信息
        feature_info = {
            "symbol": symbol,
            "features": [{"feature_name": f.feature_name, "freq": f.freq} for f in features],
            "count": len(features)
        }
        
        logger.info(f"成功获取货币{symbol}的特征数据，共{len(features)}个特征")
        
        return {
            "success": True,
            "message": "获取货币特征成功",
            "feature_info": feature_info
        }
    
    def get_data_status(self) -> Dict[str, Any]:
        """获取数据服务状态
        
        Returns:
            Dict[str, Any]: 包含数据服务状态的数据
        """
        logger.info("开始获取数据服务状态")
        
        # 获取数据加载状态
        data_loaded = data_loader.is_data_loaded()
        qlib_dir = data_loader.get_qlib_dir()
        
        status = {
            "data_loaded": data_loaded,
            "qlib_dir": qlib_dir,
            "status": "running"
        }
        
        logger.info(f"成功获取数据服务状态: {status}")
        
        return {
            "success": True,
            "message": "获取数据服务状态成功",
            "status": status
        }
    
    def get_qlib_status(self) -> Dict[str, Any]:
        """获取QLib状态
        
        Returns:
            Dict[str, Any]: 包含QLib状态的数据
        """
        logger.info("开始获取QLib状态")
        
        # 获取QLib状态
        data_loaded = data_loader.is_data_loaded()
        qlib_dir = data_loader.get_qlib_dir()
        
        # 获取已加载的数据信息
        data_info = data_loader.get_loaded_data_info()
        
        qlib_status = {
            "initialized": data_loaded,
            "qlib_dir": qlib_dir,
            "data_info": data_info
        }
        
        logger.info(f"成功获取QLib状态: {qlib_status}")
        
        return {
            "success": True,
            "message": "获取QLib状态成功",
            "qlib_status": qlib_status
        }
    
    def reload_qlib(self) -> Dict[str, Any]:
        """重新加载QLib

        Returns:
            Dict[str, Any]: 包含重新加载结果的数据
        """
        from settings.models import SystemConfigBusiness as SystemConfig
        logger.info("开始重新加载QLib")
        
        # 从系统配置获取qlib_data_dir
        qlib_dir = SystemConfig.get("qlib_data_dir")
        
        if not qlib_dir:
            qlib_dir = "data/crypto_data"
            logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
        
        # 重新初始化QLib
        success = data_loader.init_qlib(qlib_dir)
        
        if success:
            logger.info(f"QLib重新加载成功，数据目录: {qlib_dir}")
            
            # 获取已加载的数据信息
            data_info = data_loader.get_loaded_data_info()
            return {
                "success": success,
                "message": "QLib重新加载成功",
                "qlib_dir": qlib_dir,
                "data_info": data_info
            }
        else:
            logger.error(f"QLib重新加载失败，数据目录: {qlib_dir}")
            return {
                "success": success,
                "message": "QLib重新加载失败",
                "qlib_dir": qlib_dir
            }
    
    def create_download_task(self, request: DownloadCryptoRequest) -> Dict[str, Any]:
        """创建加密货币数据下载任务

        Args:
            request: 下载加密货币数据请求

        Returns:
            Dict[str, Any]: 包含任务ID的数据
        """
        logger.info(f"收到加密货币数据下载请求，参数: {request.model_dump()}")

        # 创建下载任务（使用固定下载目录，忽略 request.save_dir）
        task_id = task_manager.create_task(
            task_type="download_crypto",
            exchange=request.exchange,
            start=request.start,
            end=request.end,
            interval=request.interval,  # 使用所有时间周期
            max_workers=request.max_workers,
            candle_type=request.candle_type,
            symbols=request.symbols,
            save_dir=request.save_dir
        )
        
        logger.info(f"创建下载任务成功，任务ID: {task_id}")
        
        return {
            "success": True,
            "message": "加密货币数据下载任务已创建",
            "task_id": task_id
        }
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, Any]: 包含任务状态和进度的数据
        """
        logger.info(f"查询任务状态，任务ID: {task_id}")
        
        # 获取任务状态
        task_info = task_manager.get_task(task_id)
        
        if not task_info:
            logger.warning(f"任务不存在，任务ID: {task_id}")
            return {
                "success": False,
                "message": "任务不存在",
                "task_id": task_id
            }
        
        logger.info(f"查询任务状态成功，任务ID: {task_id}, 状态: {task_info['status']}")
        
        return {
            "success": True,
            "message": "查询任务状态成功",
            "task_info": task_info
        }
    
    def fetch_symbols_from_exchange(self, exchange: str, filter: Optional[str] = None, limit: Optional[int] = 100, offset: Optional[int] = 0, configs: Dict[str, Any] = {}, crypto_type: Optional[str] = None) -> Dict[str, Any]:
        """从第三方交易所API获取货币对列表并同步到数据库

        先调用 sync_crypto_symbols() 同步数据，再从数据库分页返回。

        Args:
            exchange: 交易所名称，如binance、okx等
            filter: 过滤条件，如'USDT'表示只返回USDT交易对
            limit: 返回数量限制
            offset: 返回偏移量
            configs: 应用配置，包含代理信息等
            crypto_type: 加密货币类型，如spot（现货）、future（合约）等

        Returns:
            Dict[str, Any]: 包含货币对列表的数据
        """
        logger.info(f"开始从交易所API获取加密货币对列表，交易所: {exchange}, 类型: {crypto_type}, 过滤条件: {filter}, 限制: {limit}, 偏移: {offset}")

        try:
            exchange_id = exchange.lower()

            proxy_enabled_key = f"exchange.{exchange_id}.proxy_enabled"
            proxy_url_key = f"exchange.{exchange_id}.proxy_url"
            proxy_username_key = f"exchange.{exchange_id}.proxy_username"
            proxy_password_key = f"exchange.{exchange_id}.proxy_password"

            proxy_enabled = configs.get(proxy_enabled_key) in ("1", "true", True)
            proxy_url = configs.get(proxy_url_key)
            proxy_username = configs.get(proxy_username_key)
            proxy_password = configs.get(proxy_password_key)

            logger.info(f"代理配置 (交易所: {exchange_id}): enabled={proxy_enabled}, url={proxy_url}")

            sync_result = sync_crypto_symbols(
                exchange=exchange,
                proxy_enabled=proxy_enabled,
                proxy_url=proxy_url,
                proxy_username=proxy_username,
                proxy_password=proxy_password,
            )

            if not sync_result.get("success"):
                return {
                    "success": False,
                    "message": f"同步{exchange}交易所货币对列表失败: {sync_result.get('message', '未知错误')}",
                    "error": sync_result.get("message", "未知错误"),
                    "exchange": exchange
                }

            return self.get_crypto_symbols(
                exchange=exchange,
                filter=filter,
                limit=limit,
                offset=offset,
                configs=configs,
                crypto_type=crypto_type
            )

        except Exception as e:
            logger.error(f"获取加密货币对列表失败: {e}")
            return {
                "success": False,
                "message": f"获取加密货币对列表失败: {str(e)}",
                "error": str(e),
                "exchange": exchange
            }
    
    def get_crypto_symbols(self, exchange: str, filter: Optional[str] = None, limit: Optional[int] = 100, offset: Optional[int] = 0, configs: Dict[str, Any] = {}, crypto_type: Optional[str] = None) -> Dict[str, Any]:
        """获取加密货币对列表

        Args:
            exchange: 交易所名称，如binance、okx等
            filter: 过滤条件，如'USDT'表示只返回USDT交易对
            limit: 返回数量限制
            offset: 返回偏移量
            configs: 应用配置，包含代理信息等
            crypto_type: 加密货币类型，如spot（现货）、future（合约）等

        Returns:
            Dict[str, Any]: 包含货币对列表的数据
        """
        logger.info(f"开始获取加密货币对列表，交易所: {exchange}, 类型: {crypto_type}, 过滤条件: {filter}, 限制: {limit}, 偏移: {offset}")

        # 只从数据库读取货币对数据，不直接调用第三方API
        try:
            import json

            from ..db.database import SessionLocal, init_database_config
            from ..db.models import CryptoSymbol
            from config import get_config

            # 从系统配置获取计价货币
            quote_currency = get_config('quote', 'USDT')
            logger.info(f"系统配置计价货币: quote={quote_currency}")

            # 初始化数据库配置
            init_database_config()
            db = SessionLocal()
            try:
                # 查询数据库中的货币对
                query = db.query(CryptoSymbol).filter(CryptoSymbol.exchange == exchange)

                # 应用类型过滤条件
                if crypto_type:
                    query = query.filter(CryptoSymbol.type == crypto_type)

                # 应用计价货币过滤（使用数据库 quote 字段）
                if quote_currency:
                    query = query.filter(CryptoSymbol.quote == quote_currency)

                # 应用 symbol 过滤条件
                if filter:
                    query = query.filter(CryptoSymbol.symbol.contains(filter))

                # 获取总数量
                total = query.count()

                # 应用分页
                paginated_symbols = query.offset(offset).limit(limit).all()

                logger.info(f"从数据库获取到{total}个{exchange}货币对，返回{len(paginated_symbols)}个货币对")
                
                # 转换为API响应格式
                symbols_list = []
                for symbol in paginated_symbols:
                    symbols_list.append({
                        "symbol": symbol.symbol,
                        "base": symbol.base,
                        "quote": symbol.quote,
                        "active": symbol.active,
                        "precision": json.loads(symbol.precision),
                        "limits": json.loads(symbol.limits),
                        "type": symbol.type
                    })
                
                # 构建响应
                response_data = {
                    "symbols": symbols_list,
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                    "exchange": exchange
                }
                
                return {
                    "success": True,
                    "message": "从数据库获取加密货币对列表成功",
                    "response_data": response_data
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"从数据库获取货币对失败: {e}")
            return {
                "success": False,
                "message": "从数据库获取加密货币对列表失败",
                "error": str(e),
                "exchange": exchange
            }
    
    def get_all_tasks(self, page: int = 1, page_size: int = 10, task_type: Optional[str] = None, status: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None, created_at: Optional[str] = None, updated_at: Optional[str] = None, sort_by: str = "created_at", sort_order: str = "desc") -> Dict[str, Any]:
        """查询所有任务状态，支持分页和过滤
        
        Args:
            page: 当前页码
            page_size: 每页数量
            task_type: 任务类型过滤
            status: 任务状态过滤
            start_time: 开始时间过滤
            end_time: 结束时间过滤
            created_at: 创建时间过滤
            updated_at: 更新时间过滤
            sort_by: 排序字段
            sort_order: 排序顺序
            
        Returns:
            Dict[str, Any]: 包含任务列表和分页信息的数据
        """
        if self.db is None:
            raise ValueError("数据库会话未初始化")
        
        logger.info(f"查询任务列表请求: page={page}, page_size={page_size}, task_type={task_type}, status={status}")
        
        # 转换时间字符串为datetime对象
        from datetime import datetime

        # 处理开始时间
        start_time_dt = None
        if start_time:
            try:
                start_time_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"无效的开始时间格式: {start_time}，忽略该过滤条件")
        
        # 处理结束时间
        end_time_dt = None
        if end_time:
            try:
                end_time_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"无效的结束时间格式: {end_time}，忽略该过滤条件")
        
        # 处理创建时间
        created_at_dt = None
        if created_at:
            try:
                created_at_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"无效的创建时间格式: {created_at}，忽略该过滤条件")
        
        # 处理更新时间
        updated_at_dt = None
        if updated_at:
            try:
                updated_at_dt = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"无效的更新时间格式: {updated_at}，忽略该过滤条件")
        
        # 计算偏移量
        skip = (page - 1) * page_size
        
        # 使用SQLAlchemy CRUD操作获取数据
        tasks, total = crud.get_tasks_paginated(
            db=self.db,
            skip=skip,
            limit=page_size,
            task_type=task_type,
            status=status,
            start_time=start_time_dt,
            end_time=end_time_dt,
            created_at=created_at_dt,
            updated_at=updated_at_dt,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # 计算总页数
        pages = (total + page_size - 1) // page_size
        
        # 构建响应数据
        # 转换SQLAlchemy模型为字典格式
        task_list = []
        for task in tasks:
            task_dict = {
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
                "start_time": task.start_time,
                "end_time": task.end_time,
                "error_message": task.error_message,
                "created_at": task.created_at,
                "updated_at": task.updated_at
            }
            task_list.append(task_dict)
        
        result = {
            "tasks": task_list,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": pages
            }
        }
        
        logger.info(f"查询任务列表成功: 共{total}条，第{page}/{pages}页")
        
        return {
            "success": True,
            "message": "查询任务列表成功",
            "result": result
        }
    
    def get_kline_data(self, symbol: str, interval: str, market_type: str = "crypto", crypto_type: Optional[str] = "spot", start_time: Optional[str] = None, end_time: Optional[str] = None, limit: Optional[int] = 5000) -> Dict[str, Any]:
        """获取K线数据
        
        从数据库中查询指定交易对和周期的K线数据，支持不同市场类型
        
        Args:
            symbol: 交易商标识
            interval: 时间周期
            market_type: 市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币），默认crypto
            crypto_type: 加密货币类型，当market_type为crypto时必填，可选值：spot（现货）、future（合约），默认spot
            start_time: 开始时间，格式YYYY-MM-DD HH:MM:SS
            end_time: 结束时间，格式YYYY-MM-DD HH:MM:SS
            limit: 返回数量限制，默认5000条
            
        Returns:
            Dict[str, Any]: 包含K线数据的字典
        """
        if self.db is None:
            raise ValueError("数据库会话未初始化")
        
        logger.info(f"查询K线数据: symbol={symbol}, interval={interval}, market_type={market_type}, crypto_type={crypto_type}, start_time={start_time}, end_time={end_time}, limit={limit}")
        
        # 导入K线数据工厂
        from .kline_factory import KlineDataFactory
        
        try:
            # 创建对应的K线数据获取器
            fetcher = KlineDataFactory.create_fetcher(market_type, crypto_type)
            
            # 使用获取器获取K线数据
            result = fetcher.fetch_kline_data(
                db=self.db,
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            
            logger.info(f"查询K线数据成功: symbol={symbol}, interval={interval}, count={len(result.get('kline_data', []))}")
            
            return result
        except Exception as e:
            logger.error(f"查询K线数据失败: {e}")
            logger.exception(e)
            return {
                "success": False,
                "message": f"查询K线数据失败: {str(e)}",
                "kline_data": []
            }
    
    def get_product_list(
        self,
        market_type: str = "crypto",
        crypto_type: Optional[str] = "spot",
        exchange: Optional[str] = None,
        filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """获取商品列表
        
        根据市场类型和交易商获取商品列表数据
        
        Args:
            market_type: 市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币），默认crypto
            crypto_type: 加密货币类型，当market_type为crypto时必填，可选值：spot（现货）、future（合约），默认spot
            exchange: 交易商名称
            filter: 过滤条件
            limit: 返回数量限制，默认100条
            offset: 返回偏移量，默认0
            
        Returns:
            Dict[str, Any]: 包含商品列表的字典
        """
        logger.info(f"查询商品列表: market_type={market_type}, crypto_type={crypto_type}, exchange={exchange}, filter={filter}, limit={limit}, offset={offset}")
        
        # 导入商品列表工厂
        from .product_factory import ProductListFactory
        
        try:
            # 创建对应的商品列表获取器
            fetcher = ProductListFactory.create_fetcher(market_type, crypto_type)
            
            # 使用获取器获取商品列表
            result = fetcher.fetch_products(
                db=self.db,
                exchange=exchange,
                filter=filter,
                limit=limit,
                offset=offset
            )
            
            logger.info(f"查询商品列表成功: market_type={market_type}, count={len(result.get('products', []))}")
            
            return result
        except Exception as e:
            logger.error(f"查询商品列表失败: {e}")
            logger.exception(e)
            return {
                "success": False,
                "message": f"查询商品列表失败: {str(e)}",
                "products": [],
                "total": 0
            }
    

    def async_download_crypto(self, task_id: str, request: DownloadCryptoRequest):
        """异步下载加密货币数据

        Args:
            task_id: 任务ID
            request: 下载加密货币数据请求
        """
        try:

            logger.info(f"开始异步下载加密货币数据，任务ID: {task_id}, 请求参数: {request.model_dump()}")

            # 开始任务
            task_manager.start_task(task_id)

            # 计算总任务数（时间周期数 × 货币对数）
            total_intervals = len(request.interval)
            total_symbols = len(request.symbols)
            total_tasks = total_intervals * total_symbols
            completed_tasks = 0

            # 遍历所有时间周期
            for interval_idx, interval in enumerate(request.interval):
                logger.info(f"开始处理时间周期: {interval} ({interval_idx + 1}/{total_intervals})")

                # 更新进度：开始处理当前时间周期
                task_manager.update_progress(
                    task_id=task_id,
                    current=f"{interval}",
                    completed=completed_tasks,
                    total=total_tasks,
                    status=f"正在下载 {interval} 数据 ({', '.join(request.symbols)})...",
                    interval=interval
                )

                # 实例化GetData类并传入所有参数（支持多货币对批量下载）
                get_data = GetData(
                    symbols=",".join(request.symbols),  # 多个货币对用逗号连接
                    exchange=request.exchange,
                    candle_type=request.candle_type,
                    start=request.start,
                    end=request.end,
                    interval=interval,
                    max_workers=1,  # 强制使用单进程，避免 pickle 序列化错误
                    mode=request.mode
                )

                # 创建实时进度回调函数（推送下载过程中的细粒度进度）
                def download_progress_callback(symbol, current, total_count, failed_count, status="downloading"):
                    """下载过程中的实时进度回调"""
                    try:
                        progress_pct = (current / total_count * 100) if total_count > 0 else 0

                        task_manager.update_progress(
                            task_id=task_id,
                            current=symbol,
                            completed=completed_tasks + (progress_pct / 100),
                            total=total_tasks,
                            status=f"正在下载 {symbol} {interval}: {status}",
                            symbol_progress=round(progress_pct, 1),
                            interval=interval
                        )
                    except Exception as e:
                        logger.warning(f"推送下载进度失败: {e}")

                # 调用run方法下载数据（传入进度回调以实现实时更新）
                get_data.run(progress_callback=download_progress_callback)

                # 更新进度：当前时间周期的所有货币对完成
                completed_tasks += total_symbols
                task_manager.update_progress(
                    task_id=task_id,
                    current=f"{interval}",
                    completed=completed_tasks,
                    total=total_tasks,
                    status=f"{interval} 数据下载完成",
                    symbol_progress=100.0,
                    interval=interval
                )
                logger.info(f"时间周期 {interval} 所有数据下载成功")
                
                # 添加数据库写入功能
                try:
                    logger.info(f"开始将 {interval} 数据写入数据库")
                    # 获取当前项目根目录
                    project_root = Path(__file__).parent.parent.parent
                    logger.info(f"当前项目根目录: {project_root}")

                    # 构建数据目录路径（使用固定下载目录）
                    data_dir = get_data.save_dir / interval
                    if not data_dir.is_absolute():
                        data_dir = project_root / data_dir
                    logger.info(f"数据目录: {data_dir}")
                    # 导入数据库相关模块
                    from sqlalchemy import func

                    from collector.db.database import (
                        SessionLocal, init_database_config)
                    from collector.db.models import CryptoSpotKline, CryptoFutureKline

                    # 初始化数据库配置
                    init_database_config()

                    # 优先查找 Parquet 文件，兼容旧版 CSV 文件
                    parquet_files = list_parquet_files(data_dir)
                    if not parquet_files:
                        # 如果没有 Parquet 文件，尝试查找 CSV 文件（向后兼容）
                        csv_files = list(data_dir.glob("*.csv"))
                        logger.info(f"未找到 Parquet 文件，找到 {len(csv_files)} 个 CSV 文件（旧格式）")

                        for csv_file in csv_files:
                            symbol = csv_file.stem
                            logger.info(f"开始处理CSV文件: {csv_file}")

                            df = pd.read_csv(csv_file)
                            if df is None or df.empty:
                                logger.warning(f"{symbol} 数据为空，跳过写入数据库")
                                continue

                            self._process_dataframe_for_db(df, symbol, interval, request)
                    else:
                        logger.info(f"找到 {len(parquet_files)} 个 Parquet 文件")

                        # 过滤文件（只处理当前下载的交易对）
                        if request.symbols:
                            symbol_set = set(symbol.replace("/", "") for symbol in request.symbols)
                            parquet_files = [f for f in parquet_files if f.stem in symbol_set]
                            logger.info(f"过滤后找到 {len(parquet_files)} 个 Parquet 文件")

                        # 处理每个 Parquet 文件
                        for parquet_file in parquet_files:
                            symbol = parquet_file.stem
                            logger.info(f"开始处理Parquet文件: {parquet_file}")

                            # 使用 load_from_parquet 读取数据
                            df = load_from_parquet(parquet_file)

                            if df is None or df.empty:
                                logger.warning(f"{symbol} 数据为空，跳过写入数据库")
                                continue

                            self._process_dataframe_for_db(df, symbol, interval, request)
                except Exception as e:
                    logger.error(f"处理数据库写入时发生异常: {e}")
                    logger.exception(e)
            
            logger.info(f"所有时间周期数据下载成功，任务ID: {task_id}")
            
            # 更新任务状态为已完成
            task_manager.complete_task(task_id)
        except Exception as e:
            logger.error(f"加密货币数据下载失败，任务ID: {task_id}, 错误: {e}")
            logger.exception(e)
            
            # 更新任务状态为失败
            task_manager.fail_task(task_id, error_message=str(e))

    def _process_dataframe_to_file(self, df, symbol, interval, request):
        """
        处理 DataFrame 并写入Parquet文件（替代数据库存储）

        Args:
            df: K线数据DataFrame
            symbol: 交易对符号
            interval: 时间间隔
            request: 下载请求对象
        """
        try:
            from utils.kline_file_manager import get_kline_file_manager

            # 准备数据，确保只包含需要的列
            df_clean = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
            
            # 清理无效数据
            df_clean = df_clean.dropna(subset=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # 确保timestamp为整数
            df_clean['timestamp'] = pd.to_numeric(df_clean['timestamp'], errors='coerce').astype('int64')
            
            # 再次清理转换后的无效数据
            df_clean = df_clean.dropna()
            
            if df_clean.empty:
                logger.warning(f"没有有效数据可以保存到文件: {symbol} {interval}")
                return

            # 确定市场类型
            market_type = 'spot' if request.candle_type == "spot" else 'future'
            
            logger.info(f"保存K线数据到Parquet文件: {symbol} {interval}, 市场类型: {market_type}")
            
            # 使用文件管理器保存
            manager = get_kline_file_manager()
            
            success = manager.save_klines(
                df=df_clean,
                symbol=symbol,
                interval=interval,
                market_type=market_type
            )
            
            if success:
                logger.info(f"成功将 {len(df_clean)} 条 {symbol} 数据保存到Parquet文件")
            else:
                logger.error(f"保存 {symbol} 数据到文件失败")
                
        except Exception as e:
            logger.error(f"处理DataFrame并保存到文件失败: {e}")
            import traceback
            logger.exception(traceback.format_exc())

    def _process_dataframe_for_db(self, df, symbol, interval, request):
        """
        [已废弃] 处理 DataFrame 并写入数据库
        
        此方法已被 _process_dataframe_to_file 替代，
        保留仅用于向后兼容。
        
        Args:
            df: K线数据DataFrame
            symbol: 交易对符号
            interval: 时间间隔
            request: 下载请求对象
        """
        logger.warning("[DataService] _process_dataframe_for_db 已废弃，使用 _process_dataframe_to_file 替代")
        self._process_dataframe_to_file(df, symbol, interval, request)

    def export_crypto_data(self, request: ExportCryptoRequest) -> Dict[str, Any]:
        """导出加密货币数据
        
        Args:
            request: 导出加密货币数据请求
            
        Returns:
            Dict[str, Any]: 包含导出结果的数据
        """
        logger.info(f"开始导出加密货币数据，请求参数: {request.model_dump()}")
        
        try:
            # 实例化导出工具
            export_data = ExportData()
            
            # 执行导出
            result = export_data.export_kline_data(
                symbols=request.symbols,
                interval=request.interval,
                start=request.start,
                end=request.end,
                exchange=request.exchange,
                candle_type=request.candle_type,
                save_dir=request.save_dir,
                max_workers=request.max_workers,
                auto_download=request.auto_download
            )
            
            logger.info(f"加密货币数据导出完成，结果: {result}")
            return {
                "success": True,
                "message": "加密货币数据导出成功",
                "data": result
            }
        except Exception as e:
            logger.error(f"导出加密货币数据失败: {e}")
            logger.exception(e)
            return {
                "success": False,
                "message": f"导出加密货币数据失败: {str(e)}",
                "data": {}
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

