# 数据服务模块
# 整合数据下载、导出、加密货币对同步、K线数据管理等功能。
# 支持 Parquet 格式本地存储，提供更高的压缩率和查询性能。

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import pandas as pd
from sqlalchemy import and_

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

from exchange import BinanceCollector, OKXCollector
from utils.timestamp_utils import convert_to_datetime

from ..db import crud
from ..db.database import SessionLocal, init_database_config
from ..db.models import CryptoFutureKline, CryptoSpotKline, CryptoSymbol, StockKline
from ..utils.task_manager import task_manager

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..schemas.data import (
        DownloadCryptoRequest,
        ExportCryptoRequest,
    )

# 基础源数据目录：项目后端根目录的 data/source 目录
SOURCE_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "source"


def get_crypto_kline_dir(exchange_type: str = "spot", data_type: str = "klines") -> Path:
    """获取加密货币K线数据保存目录

    Args:
        exchange_type: 交易所类型 ("spot" 现货 或 "future" 合约)
        data_type: 数据类型 ("klines" K线数据 等)

    Returns:
        Path: 数据保存目录路径，格式为 data/source/crypto/{exchange_type}/{data_type}
    """
    return SOURCE_DATA_DIR / "crypto" / exchange_type / data_type


def get_source_data_root() -> Path:
    """获取源数据根目录（不包含子结构）

    Returns:
        Path: data/source 目录路径
    """
    return SOURCE_DATA_DIR


# 默认保存目录改为根目录（避免重复拼接，让 GetData.run() 负责唯一的一次路径构建）
default_save_dir = get_source_data_root()  # 返回: backend/data/source ✅


class GetData:
    """数据下载工具类

    提供从各种交易所下载数据的统一接口。
    支持币安(Binance)和OKX交易所。
    """

    def __init__(
        self,
        symbols=None,
        exchange="binance",
        candle_type="spot",
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
        mode="inc",
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

    def run(self, start_date=None, progress_callback=None):
        actual_start = start_date or self.start
        # 构建完整保存路径: {save_dir}/crypto/{spot|future}/klines/{interval}
        market_type = "spot" if self.candle_type == "spot" else "future"
        full_save_dir = self.save_dir / "crypto" / market_type / "klines" / self.interval

        symbols_str = ",".join(self.symbols) if isinstance(self.symbols, list) else self.symbols

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
                    symbols=symbols_str.split(",") if symbols_str else None,
                    mode=self.mode,
                )
                collector.collect_data(progress_callback=progress_callback)

            elif exchange_lower == "okx":
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
                    symbols=symbols_str.split(",") if symbols_str else None,
                    mode=self.mode,
                )
                collector.collect_data(progress_callback=progress_callback)

            else:
                logger.error(f"不支持的交易所: {self.exchange}")
                msg = f"不支持的交易所: {self.exchange}"
                raise ValueError(msg)

            logger.info(f"{self.exchange} 数据下载完成！")

        except Exception as e:
            logger.error(f"数据下载失败: {e}")
            logger.exception(e)
            raise


class ExportData:
    """数据导出工具类

    提供从数据库导出K线数据到CSV文件的功能。
    """

    # candle_type -> K线数据模型映射（与数据库建表一一对应）
    _KLINE_MODELS = {
        "spot": CryptoSpotKline,
        "future": CryptoFutureKline,
        "stock": StockKline,
    }

    def __init__(self, db=None):
        # 支持外部注入会话便于测试；未注入时自建会话并确保数据库配置已初始化
        # 用标志记录会话所有权，finally 里据此决定是否关闭（外部会话由调用方管理）
        self._owns_session = db is None
        if self._owns_session:
            init_database_config()
            self.db = SessionLocal()
        else:
            self.db = db

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
        # ponytail: max_workers/auto_download 暂未实现（串行导出、缺失数据只记录不补抓），
        # 数据量上来后再引入线程池或触发下载任务
        model = self._KLINE_MODELS.get(candle_type)
        if model is None:
            raise ValueError(f"不支持的candle_type: {candle_type}，可选: {list(self._KLINE_MODELS)}")

        export_dir = Path(save_dir) if save_dir else SOURCE_DATA_DIR / "export"
        export_dir.mkdir(parents=True, exist_ok=True)

        result = {"success": True, "exported_files": [], "missing_ranges": {}}

        try:
            logger.info(f"开始导出K线数据: 交易对={symbols}, 区间={start}至{end}, 周期={interval}")

            for symbol in symbols:
                # 数据库中 symbol 存在带斜杠与不带斜杠两种写法，两种格式都兼容
                raw_symbol = symbol.replace("/", "")
                klines = (
                    self.db.query(model)
                    .filter(and_(model.symbol.in_([symbol, raw_symbol]), model.interval == interval))
                    .all()
                )

                df = pd.DataFrame(
                    [
                        {
                            "timestamp": k.timestamp,
                            "open": float(k.open),
                            "high": float(k.high),
                            "low": float(k.low),
                            "close": float(k.close),
                            "volume": float(k.volume),
                        }
                        for k in klines
                    ]
                )

                if df.empty:
                    result["missing_ranges"][symbol] = [{"error": "数据库中无该品种数据"}]
                    continue

                # timestamp 为自适应精度的字符串存储，统一转 datetime 后再按时间范围过滤与排序
                df["dt"] = convert_to_datetime(df["timestamp"])
                df.sort_values("dt", inplace=True)

                if start:
                    # 库内时间戳统一视作 UTC，与 convert_to_datetime 的 UTC 输出对齐
                    df = df[df["dt"] >= pd.Timestamp(start, tz="UTC")]
                if end:
                    df = df[df["dt"] <= pd.Timestamp(end, tz="UTC")]

                if df.empty:
                    result["missing_ranges"][symbol] = [{"error": "指定时间范围内无数据"}]
                    continue

                export_path = export_dir / f"{raw_symbol}_{interval}.csv"
                df.drop(columns="dt").to_csv(export_path, index=False)
                result["exported_files"].append(str(export_path))
                logger.info(f"已导出 {symbol} {interval}: {len(df)} 条 -> {export_path}")

        except Exception as e:
            logger.error(f"导出失败: {e}")
            logger.exception(e)
            result["success"] = False
            result["missing_ranges"] = {symbol: [{"error": str(e)}] for symbol in symbols}
        finally:
            # 仅关闭自建会话，外部注入的会话由调用方管理
            if self._owns_session:
                self.db.close()

        return result


def sync_crypto_symbols(
    exchange: str = "binance",
    proxy_enabled: bool = False,
    proxy_url: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    log_level: str = "info",
) -> dict[str, Any]:
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

            if parsed_url.scheme in ["socks5", "socks4", "socks4a"]:
                exchange_instance.proxy = proxy_url
                proxy_configured = True
            else:
                exchange_instance.proxies = {"http": proxy_url, "https": proxy_url}
                proxy_configured = True
            if proxy_username and proxy_password:
                exchange_instance.proxy_auth = (proxy_username, proxy_password)
        else:
            env_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
            if env_proxy:
                logger.info(f"使用环境变量中的代理: {env_proxy}")
                parsed_url = urlparse(env_proxy)

                if parsed_url.scheme in ["socks5", "socks4", "socks4a"]:
                    exchange_instance.proxy = env_proxy
                    proxy_configured = True
                else:
                    exchange_instance.proxies = {"http": env_proxy, "https": env_proxy}
                    proxy_configured = True

        if not proxy_configured:
            logger.warning("未配置代理，直接访问交易所API可能会失败")

        markets = exchange_instance.load_markets()

        valid_symbols = []
        for symbol, market in markets.items():
            if market.get("active", True):
                symbol_info = {
                    "symbol": symbol,
                    "base": market.get("base"),
                    "quote": market.get("quote"),
                    "exchange": exchange,
                    "active": market.get("active"),
                    "precision": market.get("precision", {}),
                    "limits": market.get("limits", {}),
                    "type": market.get("type"),
                }
                valid_symbols.append(symbol_info)

        logger.info(f"获取到{len(valid_symbols)}个有效的{exchange}货币对")

        logger.info(f"开始保存{exchange}货币对到数据库...")

        init_database_config()

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                from utils.db_session import get_db_session

                logger.info(f"开始数据库操作，重试次数: {retry_count + 1}/{max_retries}")
                with get_db_session() as db:
                    logger.info(f"开始处理{exchange}的货币对数据...")

                    logger.info(f"获取{exchange}的现有货币对数据...")
                    existing_symbols = db.query(CryptoSymbol).filter_by(exchange=exchange).all()
                    existing_symbol_map = {sym.symbol: sym for sym in existing_symbols}
                    logger.info(f"已获取{exchange}的{len(existing_symbol_map)}条现有货币对数据")

                    new_symbol_map = {sym["symbol"]: sym for sym in valid_symbols}

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
                        precision_str = json.dumps(symbol_info["precision"])
                        limits_str = json.dumps(symbol_info["limits"])

                        if symbol in existing_symbol_map:
                            existing_sym = existing_symbol_map[symbol]
                            existing_sym.active = symbol_info["active"]
                            existing_sym.is_deleted = False
                            existing_sym.precision = precision_str
                            existing_sym.limits = limits_str
                            existing_sym.type = symbol_info["type"]
                            updated_count += 1
                        else:
                            new_symbol = CryptoSymbol(
                                symbol=symbol_info["symbol"],
                                base=symbol_info["base"],
                                quote=symbol_info["quote"],
                                exchange=symbol_info["exchange"],
                                active=symbol_info["active"],
                                precision=precision_str,
                                limits=limits_str,
                                type=symbol_info["type"],
                                is_deleted=False,
                            )
                            db.add(new_symbol)
                            inserted_count += 1

                    db.commit()
                    logger.info(
                        f"成功处理{exchange}货币对数据: 更新{updated_count}条，插入{inserted_count}条，标记删除{deleted_count}条"
                    )

                    return {
                        "success": True,
                        "message": f"成功同步{len(valid_symbols)}个{exchange}货币对到数据库",
                        "exchange": exchange,
                        "symbol_count": len(valid_symbols),
                        "updated_count": updated_count,
                        "inserted_count": inserted_count,
                        "deleted_count": deleted_count,
                        "timestamp": datetime.now().isoformat(),
                    }

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
            "success": False,
            "message": f"同步失败: {error_msg}",
            "exchange": exchange,
            "proxy_enabled": proxy_enabled,
            "proxy_url": proxy_url,
            "timestamp": datetime.now().isoformat(),
        }


class DataService:
    """数据服务类，处理数据相关的业务逻辑"""

    def __init__(self, db: Session | None = None):
        """初始化数据服务

        Args:
            db: 数据库会话，可选
        """
        self.db = db

    def get_features(self, symbol: str | None = None) -> dict[str, Any]:
        """获取特征信息

        Args:
            symbol: 可选，指定货币名称

        Returns:
            Dict[str, Any]: 包含特征信息的数据
        """
        if self.db is None:
            msg = "数据库会话未初始化"
            raise ValueError(msg)

        logger.info(f"开始获取特征信息，货币名称: {symbol}")

        if symbol:
            # 获取指定货币的特征
            features = crud.get_features_by_symbol(self.db, symbol)

            # 格式化特征信息
            feature_info = {
                "symbol": symbol,
                "features": [{"feature_name": f.feature_name, "freq": f.freq} for f in features],
                "count": len(features),
            }
            return {
                "success": True,
                "message": "获取货币特征成功",
                "feature_info": feature_info,
            }
        else:
            # 获取所有货币的特征
            features = crud.get_features(self.db)

            # 按货币名称分组
            features_by_symbol = {}
            for f in features:
                if f.symbol not in features_by_symbol:
                    features_by_symbol[f.symbol] = []
                features_by_symbol[f.symbol].append({"feature_name": f.feature_name, "freq": f.freq})

            # 返回所有货币的特征
            result = {"features": []}
            for sym, feats in features_by_symbol.items():
                result["features"].append({"symbol": sym, "features": feats, "count": len(feats)})

            return {"success": True, "message": "获取所有特征成功", "result": result}

    def get_symbol_features(self, symbol: str) -> dict[str, Any]:
        """获取指定货币的特征数据

        Args:
            symbol: 货币名称

        Returns:
            Dict[str, Any]: 包含指定货币特征数据的数据
        """
        if self.db is None:
            msg = "数据库会话未初始化"
            raise ValueError(msg)

        logger.info(f"开始获取货币{symbol}的特征数据")

        # 获取指定货币的特征
        features = crud.get_features_by_symbol(self.db, symbol)

        # 格式化特征信息
        feature_info = {
            "symbol": symbol,
            "features": [{"feature_name": f.feature_name, "freq": f.freq} for f in features],
            "count": len(features),
        }

        logger.info(f"成功获取货币{symbol}的特征数据，共{len(features)}个特征")

        return {
            "success": True,
            "message": "获取货币特征成功",
            "feature_info": feature_info,
        }

    def create_download_task(self, request: DownloadCryptoRequest) -> dict[str, Any]:
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
            save_dir=request.save_dir,
        )

        logger.info(f"创建下载任务成功，任务ID: {task_id}")

        return {
            "success": True,
            "message": "加密货币数据下载任务已创建",
            "task_id": task_id,
        }

    def get_task_status(self, task_id: str) -> dict[str, Any]:
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
            return {"success": False, "message": "任务不存在", "task_id": task_id}

        logger.info(f"查询任务状态成功，任务ID: {task_id}, 状态: {task_info['status']}")

        return {"success": True, "message": "查询任务状态成功", "task_info": task_info}

    def fetch_symbols_from_exchange(
        self,
        exchange: str,
        filter: str | None = None,
        limit: int | None = 100,
        offset: int | None = 0,
        configs: dict[str, Any] | None = None,
        crypto_type: str | None = None,
    ) -> dict[str, Any]:
        """从第三方交易所API获取货币对列表并同步到数据库

        先调用 sync_crypto_symbols() 同步数据，再从数据库分页返回。

        Args:
            exchange: 交易所名称，如binance、okx等
            filter: 过滤条件，如'USDT'表示只返回USDT交易对
            limit: 每页数量
            offset: 偏移量
            configs: 交易所配置
            crypto_type: 加密货币类型
            limit: 返回数量限制
            offset: 返回偏移量
            configs: 应用配置，包含代理信息等
            crypto_type: 加密货币类型，如spot（现货）、future（合约）等

        Returns:
            Dict[str, Any]: 包含货币对列表的数据
        """
        configs = configs or {}
        logger.info(
            f"开始从交易所API获取加密货币对列表，交易所: {exchange}, 类型: {crypto_type}, 过滤条件: {filter}, 限制: {limit}, 偏移: {offset}"
        )

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
                    "exchange": exchange,
                }

            return self.get_crypto_symbols(
                exchange=exchange,
                filter=filter,
                limit=limit,
                offset=offset,
                configs=configs,
                crypto_type=crypto_type,
            )

        except Exception as e:
            logger.error(f"获取加密货币对列表失败: {e}")
            return {
                "success": False,
                "message": f"获取加密货币对列表失败: {e!s}",
                "error": str(e),
                "exchange": exchange,
            }

    def get_crypto_symbols(
        self,
        exchange: str,
        filter: str | None = None,
        limit: int | None = 100,
        offset: int | None = 0,
        configs: dict[str, Any] | None = None,
        crypto_type: str | None = None,
    ) -> dict[str, Any]:
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
        configs = configs or {}
        logger.info(
            f"开始获取加密货币对列表，交易所: {exchange}, 类型: {crypto_type}, 过滤条件: {filter}, 限制: {limit}, 偏移: {offset}"
        )

        # 只从数据库读取货币对数据，不直接调用第三方API
        try:
            import json

            from config import get_config
            from utils.db_session import get_db_session

            from ..db.models import CryptoSymbol

            # 从系统配置获取计价货币
            quote_currency = get_config("quote", "USDT")
            logger.info(f"系统配置计价货币: quote={quote_currency}")

            with get_db_session() as db:
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
                    symbols_list.append(
                        {
                            "symbol": symbol.symbol,
                            "base": symbol.base,
                            "quote": symbol.quote,
                            "active": symbol.active,
                            "precision": json.loads(symbol.precision),
                            "limits": json.loads(symbol.limits),
                            "type": symbol.type,
                        }
                    )

                # 构建响应
                response_data = {
                    "symbols": symbols_list,
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                    "exchange": exchange,
                }

                return {
                    "success": True,
                    "message": "从数据库获取加密货币对列表成功",
                    "response_data": response_data,
                }
        except Exception as e:
            logger.error(f"从数据库获取货币对失败: {e}")
            return {
                "success": False,
                "message": "从数据库获取加密货币对列表失败",
                "error": str(e),
                "exchange": exchange,
            }

    def get_all_tasks(
        self,
        page: int = 1,
        page_size: int = 10,
        task_type: str | None = None,
        status: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
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
            msg = "数据库会话未初始化"
            raise ValueError(msg)

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
            sort_order=sort_order,
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
                    "percentage": task.percentage,
                },
                "params": json.loads(task.params),
                "start_time": task.start_time,
                "end_time": task.end_time,
                "error_message": task.error_message,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
            task_list.append(task_dict)

        result = {
            "tasks": task_list,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": pages,
            },
        }

        logger.info(f"查询任务列表成功: 共{total}条，第{page}/{pages}页")

        return {"success": True, "message": "查询任务列表成功", "result": result}

    def get_kline_data(
        self,
        symbol: str,
        interval: str,
        market_type: str = "crypto",
        crypto_type: str | None = "spot",
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = 5000,
    ) -> dict[str, Any]:
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
            msg = "数据库会话未初始化"
            raise ValueError(msg)

        logger.info(
            f"查询K线数据: symbol={symbol}, interval={interval}, market_type={market_type}, crypto_type={crypto_type}, start_time={start_time}, end_time={end_time}, limit={limit}"
        )

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
                limit=limit,
            )

            logger.info(
                f"查询K线数据成功: symbol={symbol}, interval={interval}, count={len(result.get('kline_data', []))}"
            )

            return result
        except Exception as e:
            logger.error(f"查询K线数据失败: {e}")
            logger.exception(e)
            return {
                "success": False,
                "message": f"查询K线数据失败: {e!s}",
                "kline_data": [],
            }

    def get_product_list(
        self,
        market_type: str = "crypto",
        crypto_type: str | None = "spot",
        exchange: str | None = None,
        filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
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
        logger.info(
            f"查询商品列表: market_type={market_type}, crypto_type={crypto_type}, exchange={exchange}, filter={filter}, limit={limit}, offset={offset}"
        )

        # 导入商品列表工厂
        from .product_factory import ProductListFactory

        try:
            # 创建对应的商品列表获取器
            fetcher = ProductListFactory.create_fetcher(market_type, crypto_type)

            # 使用获取器获取商品列表
            result = fetcher.fetch_products(db=self.db, exchange=exchange, filter=filter, limit=limit, offset=offset)

            logger.info(f"查询商品列表成功: market_type={market_type}, count={len(result.get('products', []))}")

            return result
        except Exception as e:
            logger.error(f"查询商品列表失败: {e}")
            logger.exception(e)
            return {
                "success": False,
                "message": f"查询商品列表失败: {e!s}",
                "products": [],
                "total": 0,
            }

    def async_download_crypto(self, task_id: str, request: DownloadCryptoRequest):
        """异步下载加密货币数据

        根据 data_type 路由到不同的采集路径：
        - K 线类（kline/markPriceKlines/indexPriceKlines/premiumIndexKlines）：
          沿用原有 GetData 多周期遍历逻辑
        - 归档/衍生类：通过 DataCollector.collect() 统一入口
        """
        try:
            from ..schemas.data import _KLINE_TYPES

            logger.info(f"开始异步下载加密货币数据，任务ID: {task_id}, 请求参数: {request.model_dump()}")

            # 开始任务
            task_manager.start_task(task_id)

            # K 线类：沿用原有逻辑（遍历时间周期）
            if request.data_type in _KLINE_TYPES:
                self._async_download_kline(task_id, request)
            else:
                # 归档/衍生类：使用 DataCollector 统一入口
                self._async_download_other(task_id, request)

            # 更新任务状态为已完成
            task_manager.complete_task(task_id)
        except Exception as e:
            logger.error(f"加密货币数据下载失败，任务ID: {task_id}, 错误: {e}")
            logger.exception(e)

            # 更新任务状态为失败
            task_manager.fail_task(task_id, error_message=str(e))

    def _async_download_kline(self, task_id: str, request: DownloadCryptoRequest):
        """K线类异步下载（原有逻辑）"""
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
                interval=interval,
            )

            # 实例化GetData类并传入所有参数
            get_data = GetData(
                symbols=",".join(request.symbols),
                exchange=request.exchange,
                candle_type=request.candle_type,
                start=request.start,
                end=request.end,
                interval=interval,
                max_workers=1,
                mode=request.mode,
            )

            # 创建实时进度回调
            symbol_completed = 0

            def download_progress_callback(symbol, current, total_count, failed_count, status="downloading"):
                nonlocal symbol_completed
                try:
                    symbol_progress_pct = (current / total_count * 100) if total_count > 0 else 0

                    if status in ["completed", "failed"] and symbol_progress_pct >= 99.9:
                        symbol_completed += 1

                    task_manager.update_progress(
                        task_id=task_id,
                        current=symbol,
                        completed=symbol_progress_pct,
                        total=100,
                        status=f"[{symbol_completed + 1}/{total_symbols}] {symbol} {interval}: {status}",
                        symbol_progress=round(symbol_progress_pct, 1),
                        interval=interval,
                    )
                except Exception as e:
                    logger.warning(f"推送下载进度失败: {e}")

            get_data.run(progress_callback=download_progress_callback)

            completed_tasks += total_symbols

            task_manager.update_progress(
                task_id=task_id,
                current=f"{interval}",
                completed=100,
                total=100,
                status=f"[{completed_tasks}/{total_symbols * total_intervals}] {interval} 数据下载完成",
                symbol_progress=100.0,
                interval=interval,
            )
            logger.info(f"时间周期 {interval} 所有数据下载成功")

        logger.info(f"所有时间周期数据下载成功，任务ID: {task_id}")

        total_task_count = total_symbols * total_intervals
        task_manager.update_progress(
            task_id=task_id,
            current="完成",
            completed=completed_tasks,
            total=total_task_count,
            status="全部下载完成",
            symbol_progress=100.0,
            interval="all",
        )

    def _async_download_other(self, task_id: str, request: DownloadCryptoRequest):
        """归档/衍生类异步下载"""
        from ..services.data_collector import DataCollector

        logger.info(f"使用 DataCollector 下载 {request.data_type} 数据，市场: {request.market}")

        total_symbols = len(request.symbols)
        completed = 0

        for symbol in request.symbols:
            task_manager.update_progress(
                task_id=task_id,
                current=symbol,
                completed=int(completed / max(total_symbols, 1) * 100),
                total=100,
                status=f"正在下载 {request.data_type} ({request.market}) {symbol}...",
                interval="",
            )

            try:
                collector = DataCollector()
                collector.collect(
                    data_type=request.data_type,
                    market=request.market,
                    symbols=[symbol],
                    intervals=request.interval or None,
                    start=request.start,
                    end=request.end,
                )
                logger.info(f"{symbol} {request.data_type} 下载成功")
            except Exception as e:
                logger.error(f"{symbol} {request.data_type} 下载失败: {e}")

            completed += 1

        task_manager.update_progress(
            task_id=task_id,
            current="完成",
            completed=100,
            total=100,
            status=f"{request.data_type} 数据下载完成（{completed}/{total_symbols}）",
            interval="",
        )

    def export_crypto_data(self, request: ExportCryptoRequest) -> dict[str, Any]:
        """导出加密货币数据

        Args:
            request: 导出加密货币数据请求

        Returns:
            Dict[str, Any]: 包含导出结果的数据
        """
        logger.info(f"开始导出加密货币数据，请求参数: {request.model_dump()}")

        try:
            # 实例化导出工具（复用当前服务的数据库会话）
            export_data = ExportData(db=self.db)

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
                auto_download=request.auto_download,
            )

            logger.info(f"加密货币数据导出完成，结果: {result}")
            return {"success": True, "message": "加密货币数据导出成功", "data": result}
        except Exception as e:
            logger.error(f"导出加密货币数据失败: {e}")
            logger.exception(e)
            return {
                "success": False,
                "message": f"导出加密货币数据失败: {e!s}",
                "data": {},
            }


class CryptoSymbolService:
    """加密货币对同步服务类

    提供加密货币对同步相关的业务逻辑
    """

    @staticmethod
    def sync_symbols(
        exchange: str = "binance",
        proxy_enabled: bool = False,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ) -> dict[str, Any]:
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
        exchanges: list | None = None,
        proxy_enabled: bool = False,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
    ) -> dict[str, Any]:
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
            exchanges = ["binance"]

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
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }
