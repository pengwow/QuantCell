"""collector.services.data_service 单元测试。

覆盖:
- GetData.run: binance/okx/不支持的交易所分支、symbols 字符串与列表、start_date 覆盖
- sync_crypto_symbols: ccxt 市场拉取、代理配置（显式/环境变量）、数据库 upsert、
  锁冲突重试、失败返回结构
- DataService: get_features / get_symbol_features / create_download_task /
  get_task_status / fetch_symbols_from_exchange / get_crypto_symbols /
  get_all_tasks / get_kline_data / get_product_list / async_download_crypto /
  _async_download_kline / _async_download_other / export_crypto_data
- CryptoSymbolService: sync_symbols / sync_all_exchanges 委托
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Worker.relationship("Strategy") 是字符串引用，两个 mapper 模块都注册后 configure 才能通过，
# 否则在真实构造 CryptoSymbol 时触发 SQLAlchemy mapper 配置失败
import strategy.models
import worker.models
from collector.services.data_service import (
    CryptoSymbolService,
    DataService,
    ExportData,
    GetData,
    sync_crypto_symbols,
)


def make_markets() -> dict:
    """构造 ccxt load_markets 返回的市场快照（两个活跃交易对 + 一个不活跃）。"""
    return {
        "BTCUSDT": {
            "active": True,
            "base": "BTC",
            "quote": "USDT",
            "precision": {"amount": 8},
            "limits": {"amount": {"min": 1e-5}},
            "type": "spot",
        },
        "ETHUSDT": {
            "active": True,
            "base": "ETH",
            "quote": "USDT",
            "precision": {"amount": 8},
            "limits": {},
            "type": "spot",
        },
        "USDCUSDT": {
            "active": False,
            "base": "USDC",
            "quote": "USDT",
            "precision": {},
            "limits": {},
            "type": "spot",
        },
    }


def patch_ccxt_and_db(markets, existing_symbols):
    """按 sync_crypto_symbols 的导入方式拼好 ccxt 与 db 会话的 mock。"""
    mock_exchange = MagicMock()
    mock_exchange.load_markets.return_value = markets
    exchange_patch = patch("ccxt.binance", return_value=mock_exchange)

    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.all.return_value = existing_symbols
    db_ctx = MagicMock()
    db_ctx.__enter__.return_value = mock_db
    db_patch = patch("utils.db_session.get_db_session", return_value=db_ctx)
    return exchange_patch, db_patch, mock_exchange, mock_db


# =================== GetData ===================


class TestGetData:
    def test_run_binance_downloads_with_expected_params(self, tmp_path):
        gd = GetData(
            symbols=["BTCUSDT", "ETHUSDT"],
            exchange="binance",
            candle_type="spot",
            save_dir=str(tmp_path),
            start="2024-01-01",
            end="2024-01-31",
            interval="1d",
            mode="inc",
        )
        with patch("collector.services.data_service.BinanceCollector") as mock_cls:
            gd.run()

        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["save_dir"] == Path(tmp_path) / "crypto/spot/klines/1d"
        assert kwargs["symbols"] == ["BTCUSDT", "ETHUSDT"]
        assert kwargs["candle_type"] == "spot"
        assert kwargs["mode"] == "inc"
        mock_cls.return_value.collect_data.assert_called_once()

    def test_run_accepts_symbols_as_str(self):
        gd = GetData(symbols="BTCUSDT,ETHUSDT", exchange="binance")
        with patch("collector.services.data_service.BinanceCollector") as mock_cls:
            gd.run()
        assert mock_cls.call_args.kwargs["symbols"] == ["BTCUSDT", "ETHUSDT"]

    def test_run_future_candle_type_uses_future_dir(self):
        gd = GetData(symbols=["BTCUSDT"], exchange="binance_futures", candle_type="future")
        with patch("collector.services.data_service.BinanceCollector") as mock_cls:
            gd.run()
        save_dir = mock_cls.call_args.kwargs["save_dir"]
        assert save_dir.parts[-4:] == ("crypto", "future", "klines", "1d")

    def test_run_okx_branch(self):
        gd = GetData(symbols=["BTCUSDT"], exchange="okx")
        with patch("collector.services.data_service.OKXCollector") as mock_cls:
            gd.run()
        mock_cls.assert_called_once()
        mock_cls.return_value.collect_data.assert_called_once()

    def test_run_start_date_overrides_instance_start(self):
        gd = GetData(symbols=["BTCUSDT"], exchange="binance", start="2024-01-01")
        with patch("collector.services.data_service.BinanceCollector") as mock_cls:
            gd.run(start_date="2023-01-01")
        assert mock_cls.call_args.kwargs["start"] == "2023-01-01"

    def test_run_unsupported_exchange_raises(self):
        gd = GetData(symbols=["BTCUSDT"], exchange="huobi")
        with (
            patch("collector.services.data_service.BinanceCollector"),
            patch("collector.services.data_service.OKXCollector"),
        ):
            with pytest.raises(ValueError, match="不支持的交易所"):
                gd.run()

    def test_run_re_raises_collector_error(self):
        gd = GetData(symbols=["BTCUSDT"], exchange="binance")
        with patch("collector.services.data_service.BinanceCollector") as mock_cls:
            mock_cls.return_value.collect_data.side_effect = RuntimeError("boom")
            with pytest.raises(RuntimeError, match="boom"):
                gd.run()

    def test_run_passes_progress_callback(self):
        gd = GetData(symbols=["BTCUSDT"], exchange="binance")

        def callback(*_args, **_kwargs):
            return None

        with patch("collector.services.data_service.BinanceCollector") as mock_cls:
            gd.run(progress_callback=callback)
        mock_cls.return_value.collect_data.assert_called_once_with(progress_callback=callback)


# =================== sync_crypto_symbols ===================


class TestSyncCryptoSymbols:
    def test_sync_upserts_new_deactivates_missing(self):
        existing = [MagicMock(symbol="BTCUSDT"), MagicMock(symbol="OLDUSDT")]
        ex_patch, db_patch, _mock_exchange, mock_db = patch_ccxt_and_db(make_markets(), existing)
        with ex_patch, db_patch, patch("collector.services.data_service.init_database_config"):
            result = sync_crypto_symbols(exchange="binance")

        assert result["success"] is True
        assert result["symbol_count"] == 2  # 不活跃的 USDCUSDT 被跳过
        assert result["updated_count"] == 1  # BTCUSDT 走更新
        assert result["inserted_count"] == 1  # ETHUSDT 走插入
        assert result["deleted_count"] == 1  # OLDUSDT 标记删除
        # 旧 symbol 被标记失效
        assert existing[1].is_deleted is True
        assert existing[1].active is False
        # 新 symbol 入库并提交
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_sync_uses_explicit_http_proxy(self):
        ex_patch, db_patch, mock_exchange, _ = patch_ccxt_and_db(make_markets(), [])
        with ex_patch, db_patch, patch("collector.services.data_service.init_database_config"):
            sync_crypto_symbols(
                exchange="binance",
                proxy_enabled=True,
                proxy_url="http://proxy.local:1080",
            )

        assert mock_exchange.proxies == {
            "http": "http://proxy.local:1080",
            "https": "http://proxy.local:1080",
        }

    def test_sync_reads_env_proxy_when_not_configured(self):
        ex_patch, db_patch, mock_exchange, _ = patch_ccxt_and_db(make_markets(), [])
        with (
            ex_patch,
            db_patch,
            patch("collector.services.data_service.init_database_config"),
            patch.dict("os.environ", {"HTTP_PROXY": "http://env.proxy:8080"}),
        ):
            sync_crypto_symbols(exchange="binance")

        assert mock_exchange.proxies == {"http": "http://env.proxy:8080", "https": "http://env.proxy:8080"}

    def test_sync_socks5_proxy_sets_proxy_field(self):
        ex_patch, db_patch, mock_exchange, _ = patch_ccxt_and_db(make_markets(), [])
        with ex_patch, db_patch, patch("collector.services.data_service.init_database_config"):
            sync_crypto_symbols(
                exchange="binance",
                proxy_enabled=True,
                proxy_url="socks5://proxy.local:1080",
            )

        assert mock_exchange.proxy == "socks5://proxy.local:1080"
        # socks 系分支只设置 proxy 单字段，不应给 proxies 赋值（MagicMock 任意属性可访问，需查 __dict__）
        assert "proxies" not in mock_exchange.__dict__

    def test_sync_lock_retry_succeeds_on_second_try(self):
        # 第一次 db 查询抛锁冲突，重试一次后成功
        first_db = MagicMock()
        first_db.query.return_value.filter_by.return_value.all.side_effect = Exception("database is locked")
        ctx1 = MagicMock()
        ctx1.__enter__.return_value = first_db

        second_symbols = [MagicMock(symbol="BTCUSDT")]
        second_db = MagicMock()
        second_db.query.return_value.filter_by.return_value.all.return_value = second_symbols
        ctx2 = MagicMock()
        ctx2.__enter__.return_value = second_db

        mock_exchange = MagicMock()
        mock_exchange.load_markets.return_value = make_markets()

        with (
            patch("ccxt.binance", return_value=mock_exchange),
            patch("utils.db_session.get_db_session", side_effect=[ctx1, ctx2]),
            patch("collector.services.data_service.init_database_config"),
            patch("collector.services.data_service.time.sleep") as mock_sleep,
        ):
            result = sync_crypto_symbols(exchange="binance")

        assert result["success"] is True
        mock_sleep.assert_called_once()

    def test_sync_non_lock_error_returns_failure(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.side_effect = RuntimeError("boom")
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_db
        mock_exchange = MagicMock()
        mock_exchange.load_markets.return_value = make_markets()

        with (
            patch("ccxt.binance", return_value=mock_exchange),
            patch("utils.db_session.get_db_session", return_value=ctx),
            patch("collector.services.data_service.init_database_config"),
        ):
            result = sync_crypto_symbols(exchange="binance")

        # 非锁类 db 错误会 e 直抛，但被外层异常兜底捕获并转为失败 dict
        assert result["success"] is False
        assert "boom" in result["message"]

    def test_sync_ccxt_failure_returns_failure_dict(self):
        mock_exchange = MagicMock()
        mock_exchange.load_markets.side_effect = RuntimeError("network down")
        with patch("ccxt.binance", return_value=mock_exchange):
            result = sync_crypto_symbols(exchange="binance")

        assert result["success"] is False
        assert "network down" in result["message"]


# =================== ExportData (会话边界) ===================


class TestExportData:
    def test_export_accepts_injected_session(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        exporter = ExportData(db=mock_db)
        result = exporter.export_kline_data(["BTCUSDT"], candle_type="spot", save_dir="/tmp")

        assert result["success"] is True
        assert "BTCUSDT" in result["missing_ranges"]
        # 外部注入的会话不应被关闭
        mock_db.close.assert_not_called()


# =================== DataService ===================


class TestDataService:
    def test_get_features_without_db_raises(self):
        svc = DataService(db=None)
        with pytest.raises(ValueError, match="数据库会话未初始化"):
            svc.get_features("BTCUSDT")

    def test_get_features_by_symbol(self, tmp_path):
        svc = DataService(db=MagicMock())
        with patch("collector.services.data_service.crud.get_features_by_symbol") as mock_get:
            mock_get.return_value = [MagicMock(feature_name="f1", freq="1d")]
            result = svc.get_features("BTCUSDT")

        assert result["success"] is True
        assert result["feature_info"]["symbol"] == "BTCUSDT"
        assert result["feature_info"]["count"] == 1
        assert result["feature_info"]["features"] == [{"feature_name": "f1", "freq": "1d"}]

    def test_get_features_grouped_by_symbol(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.data_service.crud.get_features") as mock_get:
            mock_get.return_value = [
                MagicMock(symbol="A", feature_name="f1", freq="1d"),
                MagicMock(symbol="A", feature_name="f2", freq="1h"),
                MagicMock(symbol="B", feature_name="f1", freq="1d"),
            ]
            result = svc.get_features()

        assert result["success"] is True
        assert {f["symbol"] for f in result["result"]["features"]} == {"A", "B"}
        a_group = next(f for f in result["result"]["features"] if f["symbol"] == "A")
        assert a_group["count"] == 2

    def test_get_symbol_features(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.data_service.crud.get_features_by_symbol") as mock_get:
            mock_get.return_value = [MagicMock(feature_name="f", freq="1d")]
            result = svc.get_symbol_features("BTCUSDT")
        assert result["feature_info"]["symbol"] == "BTCUSDT"

    def test_create_download_task_delegates_to_task_manager(self):
        svc = DataService(db=MagicMock())
        req = MagicMock()
        req.model_dump.return_value = {}
        req.exchange = "binance"
        req.start = None
        req.end = None
        req.interval = ["1h"]
        req.max_workers = 1
        req.candle_type = "spot"
        req.symbols = ["BTCUSDT"]
        req.save_dir = None
        with patch("collector.services.data_service.task_manager") as mock_tm:
            mock_tm.create_task.return_value = "task-1"
            result = svc.create_download_task(req)

        assert result["success"] is True
        assert result["task_id"] == "task-1"
        mock_tm.create_task.assert_called_once_with(
            task_type="download_crypto",
            exchange="binance",
            start=None,
            end=None,
            interval=["1h"],
            max_workers=1,
            candle_type="spot",
            symbols=["BTCUSDT"],
            save_dir=None,
        )

    def test_get_task_status_found(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.data_service.task_manager") as mock_tm:
            mock_tm.get_task.return_value = {"status": "running", "progress": 50}
            result = svc.get_task_status("task-1")

        assert result["success"] is True
        assert result["task_info"]["progress"] == 50

    def test_get_task_status_missing(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.data_service.task_manager") as mock_tm:
            mock_tm.get_task.return_value = None
            result = svc.get_task_status("ghost")

        assert result["success"] is False
        assert "任务不存在" in result["message"]

    def test_fetch_symbols_from_exchange_delegates_to_sync_and_list(self):
        svc = DataService(db=MagicMock())
        with (
            patch.object(svc, "get_crypto_symbols") as mock_list,
            patch("collector.services.data_service.sync_crypto_symbols") as mock_sync,
        ):
            mock_sync.return_value = {"success": True, "message": "ok"}
            mock_list.return_value = {"success": True}
            result = svc.fetch_symbols_from_exchange("binance", crypto_type="spot")

        assert result == {"success": True}
        mock_sync.assert_called_once_with(
            exchange="binance",
            proxy_enabled=False,
            proxy_url=None,
            proxy_username=None,
            proxy_password=None,
        )

    def test_fetch_symbols_from_exchange_sync_failure(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.data_service.sync_crypto_symbols") as mock_sync:
            mock_sync.return_value = {"success": False, "message": "sync boom"}
            result = svc.fetch_symbols_from_exchange("binance")

        assert result["success"] is False
        assert result["error"] == "sync boom"

    def test_get_crypto_symbols_queries_db(self):
        svc = DataService(db=MagicMock())
        mock_q = MagicMock()
        mock_q.count.return_value = 1
        mock_q.filter.return_value = mock_q  # 允许多次 filter 链式调用
        mock_q.offset.return_value.limit.return_value.all.return_value = [
            MagicMock(
                symbol="BTCUSDT",
                base="BTC",
                quote="USDT",
                active=True,
                precision='{"amount": 8}',
                limits='{"min": 0.001}',
                type="spot",
            )
        ]
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value = mock_q
        db_ctx = MagicMock()
        db_ctx.__enter__.return_value = mock_db
        with (
            patch("config.get_config", return_value="USDT"),
            patch("utils.db_session.get_db_session", return_value=db_ctx),
        ):
            result = svc.get_crypto_symbols("binance", limit=10, offset=0)

        assert result["success"] is True
        assert result["response_data"]["total"] == 1
        assert result["response_data"]["symbols"][0]["symbol"] == "BTCUSDT"
        assert result["response_data"]["symbols"][0]["precision"] == {"amount": 8}

    def test_get_crypto_symbols_failure(self):
        svc = DataService(db=MagicMock())
        with patch("config.get_config", return_value="USDT"), patch("utils.db_session.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__.side_effect = RuntimeError("db down")
            result = svc.get_crypto_symbols("binance")

        assert result["success"] is False
        assert "db down" in result["error"]

    def test_get_all_tasks_without_db_raises(self):
        svc = DataService(db=None)
        with pytest.raises(ValueError, match="数据库会话未初始化"):
            svc.get_all_tasks()

    def test_get_all_tasks_paginates(self):
        svc = DataService(db=MagicMock())
        mock_task = MagicMock()
        mock_task.task_id = "t1"
        mock_task.task_type = "download_crypto"
        mock_task.status = "running"
        mock_task.total = 10
        mock_task.completed = 3
        mock_task.failed = 1
        mock_task.current = "BTCUSDT"
        mock_task.percentage = 30
        mock_task.params = '{"a": 1}'
        mock_task.start_time = None
        mock_task.end_time = None
        mock_task.error_message = None
        mock_task.created_at = None
        mock_task.updated_at = None
        with patch("collector.services.data_service.crud.get_tasks_paginated") as mock_get:
            mock_get.return_value = ([mock_task], 1)
            result = svc.get_all_tasks(page=2, page_size=10)

        assert result["success"] is True
        assert result["result"]["pagination"]["page"] == 2
        assert result["result"]["tasks"][0]["task_id"] == "t1"
        assert result["result"]["tasks"][0]["progress"]["percentage"] == 30

    def test_get_all_tasks_ignores_bad_time_format(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.data_service.crud.get_tasks_paginated") as mock_get:
            mock_get.return_value = ([], 0)
            result = svc.get_all_tasks(start_time="not-a-date", end_time="2024-01-01 00:00:00")

        assert result["success"] is True
        assert result["result"]["tasks"] == []
        # 无效时间被忽略，其余按原字段透传
        kwargs = mock_get.call_args.kwargs
        assert kwargs["start_time"] is None
        assert kwargs["end_time"] is not None

    def test_get_kline_data(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.kline_factory.KlineDataFactory") as mock_factory:
            mock_fetcher = mock_factory.create_fetcher.return_value
            mock_fetcher.fetch_kline_data.return_value = {"success": True, "kline_data": [1]}
            result = svc.get_kline_data("BTCUSDT", "1d")

        assert result["success"] is True
        mock_factory.create_fetcher.assert_called_once_with("crypto", "spot")

    def test_get_kline_data_fetcher_error(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.kline_factory.KlineDataFactory") as mock_factory:
            mock_factory.create_fetcher.side_effect = RuntimeError("bad fetcher")
            result = svc.get_kline_data("BTCUSDT", "1d")

        assert result["success"] is False
        assert result["kline_data"] == []

    def test_get_product_list(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.product_factory.ProductListFactory") as mock_factory:
            mock_fetcher = mock_factory.create_fetcher.return_value
            mock_fetcher.fetch_products.return_value = {"success": True, "products": []}
            result = svc.get_product_list("crypto", "spot", "binance")

        assert result["success"] is True
        mock_factory.create_fetcher.assert_called_once_with("crypto", "spot")

    def test_get_product_list_factory_error(self):
        svc = DataService(db=MagicMock())
        with patch("collector.services.product_factory.ProductListFactory") as mock_factory:
            mock_factory.create_fetcher.side_effect = RuntimeError("boom")
            result = svc.get_product_list("crypto", "spot")

        assert result["success"] is False
        assert result["products"] == []

    # —— 异步任务编排 ——

    def test_async_download_kline_path(self):
        svc = DataService(db=MagicMock())
        req = MagicMock()
        req.data_type = "kline"
        req.model_dump.return_value = {}
        with (
            patch("collector.services.data_service.task_manager") as mock_tm,
            patch.object(svc, "_async_download_kline") as mock_inner,
        ):
            svc.async_download_crypto("task-1", req)

        mock_tm.start_task.assert_called_once_with("task-1")
        mock_inner.assert_called_once_with("task-1", req)
        mock_tm.complete_task.assert_called_once_with("task-1")
        mock_tm.fail_task.assert_not_called()

    def test_async_download_other_path(self):
        svc = DataService(db=MagicMock())
        req = MagicMock()
        req.data_type = "fundingRate"
        req.model_dump.return_value = {}
        with (
            patch("collector.services.data_service.task_manager") as mock_tm,
            patch.object(svc, "_async_download_other") as mock_inner,
        ):
            svc.async_download_crypto("task-2", req)

        mock_inner.assert_called_once_with("task-2", req)
        mock_tm.complete_task.assert_called_once_with("task-2")

    def test_async_download_crypto_failure_marks_failed(self):
        svc = DataService(db=MagicMock())
        req = MagicMock()
        req.data_type = "kline"
        req.model_dump.return_value = {}

        def boom(*_args):
            raise RuntimeError("broken")

        with (
            patch("collector.services.data_service.task_manager") as mock_tm,
            patch.object(svc, "_async_download_kline", side_effect=boom),
        ):
            svc.async_download_crypto("task-3", req)

        mock_tm.fail_task.assert_called_once_with("task-3", error_message="broken")
        mock_tm.complete_task.assert_not_called()

    # —— 内部异步实现 ——

    def test_async_download_kline_loop_and_progress(self):
        svc = DataService(db=MagicMock())
        req = MagicMock()
        req.interval = ["1h", "1d"]
        req.symbols = ["BTCUSDT", "ETHUSDT"]
        req.exchange = "binance"
        req.candle_type = "spot"
        req.start = None
        req.end = None
        req.mode = "inc"

        with (
            patch("collector.services.data_service.GetData") as mock_get,
            patch("collector.services.data_service.task_manager") as mock_tm,
        ):
            svc._async_download_kline("t", req)

        assert mock_get.call_count == 2  # 每个 interval 一次
        first_kwargs = mock_get.call_args_list[0].kwargs
        assert first_kwargs["symbols"] == "BTCUSDT,ETHUSDT"
        mock_tm.update_progress.assert_called()
        # 结束时的"全部下载完成"
        assert any(c.kwargs.get("status") == "全部下载完成" for c in mock_tm.update_progress.call_args_list)

    def test_async_download_other_uses_data_collector(self):
        svc = DataService(db=MagicMock())
        req = MagicMock()
        req.data_type = "fundingRate"
        req.market = "um"
        req.symbols = ["BTCUSDT"]
        req.interval = ["1h"]
        req.start = None
        req.end = None
        with (
            patch("collector.services.data_collector.DataCollector") as mock_collector,
            patch("collector.services.data_service.task_manager"),
        ):
            svc._async_download_other("t", req)

        mock_collector.return_value.collect.assert_called_once()
        kwargs = mock_collector.return_value.collect.call_args.kwargs
        assert kwargs["data_type"] == "fundingRate"
        assert kwargs["market"] == "um"
        assert kwargs["symbols"] == ["BTCUSDT"]

    def test_export_crypto_data_success(self):
        svc = DataService(db=MagicMock())
        req = MagicMock()
        req.model_dump.return_value = {}
        req.symbols = ["BTCUSDT"]
        req.interval = "1d"
        req.start = None
        req.end = None
        req.exchange = "binance"
        req.candle_type = "spot"
        req.save_dir = None
        req.max_workers = 1
        req.auto_download = True
        with patch("collector.services.data_service.ExportData") as mock_export:
            mock_export.return_value.export_kline_data.return_value = {
                "success": True,
                "exported_files": [],
            }
            result = svc.export_crypto_data(req)

        assert result["success"] is True
        mock_export.return_value.export_kline_data.assert_called_once()

    def test_export_crypto_data_failure(self):
        svc = DataService(db=MagicMock())
        req = MagicMock()
        req.model_dump.return_value = {}
        with patch("collector.services.data_service.ExportData") as mock_export:
            mock_export.return_value.export_kline_data.side_effect = RuntimeError("disk full")
            result = svc.export_crypto_data(req)

        assert result["success"] is False
        assert "disk full" in result["message"]


# =================== CryptoSymbolService ===================


class TestCryptoSymbolService:
    def test_sync_symbols_delegates(self):
        with patch("collector.services.data_service.sync_crypto_symbols") as mock_sync:
            mock_sync.return_value = {"success": True}
            result = CryptoSymbolService.sync_symbols(exchange="binance")

        assert result == {"success": True}
        mock_sync.assert_called_once_with(
            exchange="binance",
            proxy_enabled=False,
            proxy_url=None,
            proxy_username=None,
            proxy_password=None,
        )

    def test_sync_all_exchanges_aggregates_partial_failure(self):
        with patch("collector.services.data_service.sync_crypto_symbols") as mock_sync:
            mock_sync.side_effect = [{"success": True, "symbol_count": 1}, {"success": False}]
            result = CryptoSymbolService.sync_all_exchanges(["binance", "okx"])

        assert result["success"] is False  # 一个成功一个失败
        assert set(result["results"]) == {"binance", "okx"}

    def test_sync_all_exchanges_defaults_binance(self):
        with patch("collector.services.data_service.sync_crypto_symbols") as mock_sync:
            mock_sync.return_value = {"success": True}
            CryptoSymbolService.sync_all_exchanges()
        mock_sync.assert_called_once()
