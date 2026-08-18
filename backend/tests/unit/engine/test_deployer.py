"""StrategyDeployer 测试。"""

from unittest.mock import MagicMock, patch

import pytest

from credentials.exceptions import AccountNotFoundError
from credentials.service import CredentialsService
from engine.deployer import StrategyDeployer, WorkerHandle


@pytest.fixture
def db_path(tmp_path):
    """每个测试用临时 DB + 预设一个账号。"""
    db = str(tmp_path / "deployer_test.db")
    svc = CredentialsService(db_path=db)
    svc.add_account("main", "binance", "AK_TEST", "SK_TEST")
    return db


def test_deployer_dry_run_returns_handle(db_path):
    """干跑模式返回 worker handle, status=running。"""
    deployer = StrategyDeployer(dry_run=True, credentials_db=db_path)
    handle = deployer.deploy("dual_ma", "main", "BTCUSDT")
    assert isinstance(handle, WorkerHandle)
    assert handle.status == "running"
    assert handle.strategy_name == "dual_ma"
    assert handle.symbol == "BTCUSDT"
    # 干跑模式 engine_strategy_id 为空
    assert handle.engine_strategy_id is None
    assert handle.mode == "dry_run"
    deployer.stop(handle)
    assert handle.status == "stopped"


def test_deployer_account_not_found(db_path):
    """账号不存在 → AccountNotFoundError。"""
    deployer = StrategyDeployer(dry_run=True, credentials_db=db_path)
    with pytest.raises(AccountNotFoundError):
        deployer.deploy("dual_ma", "ghost_account", "BTCUSDT")


def test_deployer_unknown_strategy(db_path):
    """策略名未知 → ValueError。"""
    deployer = StrategyDeployer(dry_run=True, credentials_db=db_path)
    with pytest.raises(ValueError):
        deployer.deploy("nonexistent", "main", "BTCUSDT")


def test_deployer_list_active(db_path):
    """list_active 仅返回 running 状态。"""
    deployer = StrategyDeployer(dry_run=True, credentials_db=db_path)
    h1 = deployer.deploy("dual_ma", "main", "BTCUSDT")
    h2 = deployer.deploy("grid", "main", "ETHUSDT")
    active = deployer.list_active()
    assert len(active) == 2
    deployer.stop(h1)
    active = deployer.list_active()
    assert len(active) == 1
    assert active[0].worker_id == h2.worker_id


def test_live_mode_delegates_to_trading_engine(db_path):
    """实盘模式委托给 TradingEngine.start_strategy"""
    deployer = StrategyDeployer(dry_run=False, credentials_db=db_path)
    with patch("engine.deployer.get_trading_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_engine.start_strategy.return_value = "test_sid_123"
        mock_get_engine.return_value = mock_engine

        handle = deployer.deploy("dual_ma", "main", "BTCUSDT")
        assert handle.engine_strategy_id == "test_sid_123"
        assert handle.mode == "paper"
        mock_engine.start_strategy.assert_called_once()


def test_stop_delegates_to_engine(db_path):
    """stop 委托给 TradingEngine.stop_strategy"""
    deployer = StrategyDeployer(dry_run=False, credentials_db=db_path)
    with patch("engine.deployer.get_trading_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine

        handle = WorkerHandle(
            worker_id=__import__("uuid").uuid4(),
            strategy_name="dual_ma",
            account_name="main",
            symbol="BTCUSDT",
            status="running",
            engine_strategy_id="sid_456",
            mode="paper",
        )
        deployer.stop(handle)
        mock_engine.stop_strategy.assert_called_once_with("sid_456")
