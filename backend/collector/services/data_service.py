# 数据服务类，处理数据相关的业务逻辑
import os
from pathlib import Path
import json
from datetime import datetime
from math import log
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from ..data_loader import data_loader
from settings.models import SystemConfigBusiness as SystemConfig
from ..db import crud
from ..schemas.data import (CalendarInfoResponse, DataInfoResponse,
                            DataResponse, DownloadCryptoRequest,
                            ExportCryptoRequest, ExportCryptoResponse,
                            FeatureInfoResponse, InstrumentInfoResponse,
                            LoadDataRequest, SymbolFeaturesResponse,
                            TaskProgressResponse, TaskResponse,
                            TaskStatusResponse)
from ..scripts.export_data import ExportData
from ..utils.task_manager import task_manager


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
        
        # 如果没有接收到save_dir，则从数据库中读取
        if not request.save_dir:
            logger.info("没有接收到save_dir，从数据库中读取data_download_dir")
            data_download_dir = SystemConfig.get("data_download_dir")
            if data_download_dir:
                logger.info(f"从数据库中读取到data_download_dir: {data_download_dir}")
                request.save_dir = data_download_dir
            else:
                logger.warning("数据库中未找到data_download_dir配置")
        
        # 创建下载任务
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
        """从第三方交易所API获取货币对列表
        
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
            # 导入ccxt库
            import ccxt
            logger.info(f"配置参数: {configs}")
            # 读取代理配置
            proxy_enabled = configs.get("proxy_enabled") == "1"
            proxy_url = configs.get("proxy_url")
            proxy_username = configs.get("proxy_username")
            proxy_password = configs.get("proxy_password")
            
            logger.info(f"代理配置: enabled={proxy_enabled}, url={proxy_url}")
            
            # 创建交易所实例
            exchange_instance = getattr(ccxt, exchange)()
            # 添加超时设置
            exchange_instance.timeout = 10000  # 10秒超时
            
            # 如果启用代理，设置代理参数
            if proxy_enabled and proxy_url:
                from urllib.parse import urlparse
                parsed_url = urlparse(proxy_url)
                
                # 处理代理认证
                if proxy_username and proxy_password:
                    # 构建带认证的代理URL
                    proxy_with_auth = f"{parsed_url.scheme}://{proxy_username}:{proxy_password}@{parsed_url.netloc}{parsed_url.path}"
                    if parsed_url.scheme in ['socks5', 'socks4', 'socks4a']:
                        # SOCKS代理使用proxy属性
                        exchange_instance.proxy = proxy_with_auth
                    else:
                        # HTTP/HTTPS代理使用proxies字典
                        exchange_instance.proxies = {
                            'https': proxy_with_auth,
                            'http': proxy_with_auth
                        }
                    logger.info(f"使用带认证的代理: {proxy_with_auth}")
                else:
                    # 使用不带认证的代理
                    if parsed_url.scheme in ['socks5', 'socks4', 'socks4a']:
                        # SOCKS代理使用proxy属性
                        exchange_instance.proxy = proxy_url
                    else:
                        # HTTP/HTTPS代理使用proxies字典
                        exchange_instance.proxies = {
                            'https': proxy_url,
                            'http': proxy_url
                        }
                    logger.info(f"使用不带认证的代理: {proxy_url}")
            else:
                logger.info("未启用代理")
            
            logger.info(f"成功创建{exchange}交易所实例")
            
            # 获取货币对列表，添加错误处理
            try:
                markets = exchange_instance.fetch_markets()
                logger.info(f"成功获取{exchange}交易所的货币对列表，共{len(markets)}个货币对")
            except Exception as e:
                logger.error(f"调用{exchange}.fetch_markets()失败: {e}")
                # 返回友好的错误信息给客户端
                return {
                    "success": False,
                    "message": f"获取{exchange}交易所货币对列表失败，请检查网络连接或交易所状态",
                    "error": str(e),
                    "exchange": exchange
                }
            
            # 处理货币对列表
            symbols = []
            for market in markets:
                # 过滤无效或不活跃的货币对
                if not market.get("active", True):
                    continue
                
                # 提取必要的信息
                symbol_info = {
                    "symbol": market.get("symbol"),
                    "base": market.get("base"),
                    "quote": market.get("quote"),
                    "active": market.get("active"),
                    "precision": market.get("precision"),
                    "limits": market.get("limits"),
                    "type": market.get("type")
                }
                
                # 应用过滤条件
                if filter:
                    if filter not in symbol_info["symbol"]:
                        continue
                
                symbols.append(symbol_info)
            
            # 实现分页
            paginated_symbols = symbols[offset:offset+limit]
            
            logger.info(f"处理完成，共{len(symbols)}个符合条件的货币对，返回{len(paginated_symbols)}个货币对")
            
            # 同步到数据库
            try:
                import json

                from ..db.database import SessionLocal, init_database_config
                from ..db.models import CryptoSymbol
                
                # 初始化数据库配置
                init_database_config()
                db = SessionLocal()
                try:
                    # 先删除旧数据
                    db.query(CryptoSymbol).filter(CryptoSymbol.exchange == exchange).delete()
                    
                    # 批量插入新数据
                    crypto_symbol_objects = []
                    for symbol in symbols:
                        crypto_symbol_objects.append(CryptoSymbol(
                            symbol=symbol["symbol"],
                            base=symbol["base"],
                            quote=symbol["quote"],
                            exchange=exchange,
                            active=symbol["active"],
                            precision=json.dumps(symbol["precision"]),
                            limits=json.dumps(symbol["limits"]),
                            type=symbol["type"]
                        ))
                    
                    db.bulk_save_objects(crypto_symbol_objects)
                    db.commit()
                    logger.info(f"成功将{len(crypto_symbol_objects)}个{exchange}货币对同步到数据库")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"同步货币对到数据库失败: {e}")
                # 不影响正常返回，只记录错误
            
            # 构建响应
            response_data = {
                "symbols": paginated_symbols,
                "total": len(symbols),
                "offset": offset,
                "limit": limit,
                "exchange": exchange
            }
            
            return {
                "success": True,
                "message": "从交易所API获取加密货币对列表成功",
                "response_data": response_data
            }
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
            
            # 初始化数据库配置
            init_database_config()
            db = SessionLocal()
            try:
                # 查询数据库中的货币对
                query = db.query(CryptoSymbol).filter(CryptoSymbol.exchange == exchange)
                
                # 应用类型过滤条件
                if crypto_type:
                    query = query.filter(CryptoSymbol.type == crypto_type)
                
                # 应用过滤条件
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
    
    @staticmethod
    def async_download_crypto(task_id: str, request: DownloadCryptoRequest):
        """异步下载加密货币数据
        
        Args:
            task_id: 任务ID
            request: 下载加密货币数据请求
        """
        try:
            from pathlib import Path

            from ..scripts.get_data import GetData
            
            logger.info(f"开始异步下载加密货币数据，任务ID: {task_id}, 请求参数: {request.model_dump()}")
            
            # 开始任务
            task_manager.start_task(task_id)
            
            # 实例化GetData类
            get_data = GetData()
            
            # 定义进度回调函数
            def progress_callback(current, completed, total, failed, status=None):
                """进度回调函数
                
                Args:
                    current: 当前处理的项目
                    completed: 已完成的项目数
                    total: 总项目数
                    failed: 失败的项目数
                    status: 详细的状态描述，例如"Downloaded 2025-11-01"
                """
                # 计算进度百分比
                progress = 0
                if total > 0:
                    progress = (completed / total) * 100
                
                # 更新任务进度，传递详细的状态描述
                task_manager.update_progress(task_id, current, completed, total, failed, status)
            
            # 处理保存目录：根据接口类型拼接路径
            save_dir = request.save_dir
            if save_dir:
                # 使用Path对象处理路径，拼接crypto类型
                save_dir = Path(save_dir) / "crypto"
                logger.info(f"拼接后的保存目录: {save_dir}")
            
            # 从数据库中读取qlib_data_dir配置
            qlib_dir = SystemConfig.get("qlib_data_dir")
            if not qlib_dir:
                qlib_dir = "data/crypto_data"
                logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
            else:
                logger.info(f"从数据库中读取到qlib_data_dir: {qlib_dir}")
            
            # 遍历所有时间周期
            for interval in request.interval:
                logger.info(f"开始处理时间周期: {interval}")
                
                # 调用crypto方法下载数据
                get_data.crypto(
                    exchange=request.exchange,
                    save_dir=str(save_dir) if save_dir else None,  # 传递拼接后的save_dir参数，GetData会自动在后面添加时间周期目录
                    start=request.start,
                    end=request.end,
                    interval=interval,  # 使用当前时间周期
                    max_workers=request.max_workers,
                    candle_type=request.candle_type,
                    symbols=",".join(request.symbols),
                    convert_to_qlib=True,
                    qlib_dir=qlib_dir,  # 传递从数据库读取的qlib_data_dir作为转换地址
                    progress_callback=progress_callback,
                    mode=request.mode
                )
                
                logger.info(f"时间周期 {interval} 数据下载成功")
                
                # 添加数据库写入功能
                try:
                    logger.info(f"开始将 {interval} 数据写入数据库")
                    # 获取当前项目根目录
                    project_root = Path(__file__).parent.parent.parent
                    logger.info(f"当前项目根目录: {project_root}")

                    # 构建数据目录路径
                    data_dir = Path(save_dir) / interval if save_dir else Path(get_data.default_save_dir) / interval
                    data_dir = project_root / data_dir
                    logger.info(f"数据目录: {data_dir}")
                    # 导入数据库相关模块
                    from sqlalchemy import func, insert
                    from sqlalchemy.orm import Session

                    from backend.collector.db.database import (
                        SessionLocal, init_database_config)
                    from backend.collector.db.models import CryptoSpotKline, CryptoFutureKline

                    # 初始化数据库配置
                    init_database_config()
                    
                    # 获取所有CSV文件
                    csv_files = list(data_dir.glob("*.csv"))
                    logger.info(f"找到 {len(csv_files)} 个CSV文件")
                    
                    # 过滤文件（只处理当前下载的交易对）
                    if request.symbols:
                        symbol_set = set(symbol.replace("/", "") for symbol in request.symbols)
                        csv_files = [f for f in csv_files if f.stem in symbol_set]
                        logger.info(f"过滤后找到 {len(csv_files)} 个CSV文件")
                    
                    # 处理每个CSV文件
                    for csv_file in csv_files:
                        symbol = csv_file.stem
                        logger.info(f"开始处理文件: {csv_file}")
                        
                        # 读取CSV文件
                        df = pd.read_csv(csv_file)
                        if df is None or df.empty:
                            logger.warning(f"{symbol} 数据为空，跳过写入数据库")
                            continue
                        
                        # 准备数据，确保只包含需要的列
                        kline_list = []
                        for _, row in df.iterrows():
                            # 跳过无效行 - 使用pandas Series的isna()方法检查相关字段
                            if row[['date', 'open', 'high', 'low', 'close', 'volume']].isna().any(axis=None):
                                continue
                            
                            # 转换date列为datetime对象
                            date = row['date']
                            if isinstance(date, str):
                                date = pd.to_datetime(date)
                            
                            # 直接生成unique_kline值
                            unique_kline = f"{symbol}_{interval}_{date.isoformat()}"
                            
                            kline_list.append({
                                'symbol': symbol,
                                'interval': interval,
                                'date': date,
                                'open': row['open'],
                                'high': row['high'],
                                'low': row['low'],
                                'close': row['close'],
                                'volume': row['volume'],
                                'unique_kline': unique_kline
                            })
                        
                        if not kline_list:
                            logger.warning(f"没有有效数据可以写入数据库: {symbol}")
                            continue
                        
                        # 根据candle_type选择对应的K线模型
                        kline_model = CryptoSpotKline if request.candle_type == "spot" else CryptoFutureKline
                        logger.info(f"使用K线模型: {kline_model.__tablename__}, candle_type: {request.candle_type}")
                        
                        # 创建数据库会话
                        db = SessionLocal()
                        try:
                            # 实现跨数据库兼容的UPSERT逻辑
                            from backend.collector.db.database import db_type
                            
                            if db_type == "sqlite":
                                # SQLite使用on_conflict_do_update
                                from sqlalchemy.dialects.sqlite import \
                                    insert as sqlite_insert
                                
                                # 分批插入数据，避免SQLite变量数量超限
                                batch_size = 100
                                total_rows = len(kline_list)
                                for i in range(0, total_rows, batch_size):
                                    batch = kline_list[i:i+batch_size]
                                    stmt = sqlite_insert(kline_model).values(batch)
                                    stmt = stmt.on_conflict_do_update(
                                        index_elements=['unique_kline'],
                                        set_={
                                            'open': stmt.excluded.open,
                                            'high': stmt.excluded.high,
                                            'low': stmt.excluded.low,
                                            'close': stmt.excluded.close,
                                            'volume': stmt.excluded.volume,
                                            'updated_at': func.now()
                                        }
                                    )
                                    db.execute(stmt)
                            elif db_type == "duckdb":
                                # DuckDB使用PostgreSQL兼容的ON CONFLICT语法
                                from sqlalchemy.dialects.postgresql import \
                                    insert as pg_insert
                                stmt = pg_insert(kline_model).values(kline_list)
                                stmt = stmt.on_conflict_do_update(
                                    index_elements=['unique_kline'],
                                    set_={
                                        'open': stmt.excluded.open,
                                        'high': stmt.excluded.high,
                                        'low': stmt.excluded.low,
                                        'close': stmt.excluded.close,
                                        'volume': stmt.excluded.volume,
                                        'updated_at': func.now()
                                    }
                                )
                                db.execute(stmt)
                            else:
                                # 其他数据库类型，使用BULK INSERT + 错误处理
                                raise ValueError(f"不支持的数据库类型: {db_type}")
                        
                            db.commit()
                            logger.info(f"成功将 {len(kline_list)} 条 {symbol} 数据写入 {kline_model.__tablename__} 表")
                        except Exception as e:
                            logger.error(f"写入数据库失败: {e}")
                            logger.exception(e)
                            db.rollback()
                        finally:
                            db.close()
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
