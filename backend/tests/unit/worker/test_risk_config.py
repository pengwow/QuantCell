"""risk_config 单测：人工开关三态（enabled=True 人工配置赢 / False 强制停用 / 无行直通 params.risk）。

fallback 的 DB 访问（_load_risk_control_row）通过 mock 注入 row dict，
不连真实数据库；DB 异常吞并用 patch utils.db_session.get_db_session 钉住。
"""

from datetime import date
from unittest.mock import MagicMock, patch

import worker.risk_config as risk_config_module
from worker.risk_config import (
    RiskPnlFeeder,
    _load_risk_control_row,
    apply_risk_config,
    resolve_risk_settings,
)


def _row(**overrides) -> dict:
    """造 worker_risk_control 行 dict：默认 enabled=True 全字段空，overrides 覆盖。

    resolve/_map_row_to_settings 按键硬访问，缺键会 KeyError，统一走这里造全键行。
    """
    row = {
        "enabled": True,
        "max_position_pct": 0.0,
        "max_position_size": 0.0,
        "daily_loss_amount": None,
        "daily_loss_limit": 0.0,
        "max_drawdown": None,
        "max_leverage": None,
        "circuit_breaker_cooldown_secs": None,
    }
    row.update(overrides)
    return row


class TestResolveRiskSettings:
    def test_params_risk_passthrough(self):
        """无表行时 params.risk 直通：键原样透传，max_position_value 剥离为独立参数"""
        with patch("worker.risk_config._load_risk_control_row", return_value=None):
            settings = resolve_risk_settings(
                {"risk": {"max_daily_loss": 100.0, "max_position_value": 5000.0}},
                worker_id=1,
                initial_cash=10_000.0,
            )
        assert settings == ({"max_daily_loss": 100.0}, 5000.0)

    def test_unset_returns_none(self):
        """risk 缺失 + 表无行 → None（opt-in：驱动不注入风控，行为不变）"""
        with patch("worker.risk_config._load_risk_control_row", return_value=None):
            assert resolve_risk_settings({}, worker_id=1, initial_cash=10_000.0) is None

    def test_risk_not_dict_falls_back(self):
        """risk 非 dict（如误配成字符串）→ 忽略直通口走表行，不报错"""
        row = _row(max_position_size=3000.0)
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            settings = resolve_risk_settings({"risk": "oops"}, worker_id=1, initial_cash=10_000.0)
        assert settings is not None
        config, max_position_value = settings
        assert max_position_value == 3000.0
        assert config["max_order_value"] == 3000.0

    def test_enabled_false_beats_params_risk(self):
        """三态·强制停用：表行 enabled=False → 返回 None，人工取消赢过 params.risk"""
        row = _row(enabled=False)
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            settings = resolve_risk_settings({"risk": {"max_daily_loss": 100.0}}, worker_id=1, initial_cash=10_000.0)
        assert settings is None

    def test_enabled_true_beats_params_risk(self):
        """三态·人工配置赢：表行 enabled=True → 用表行的值而非 params.risk"""
        row = _row(max_position_pct=0.2)
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            settings = resolve_risk_settings({"risk": {"max_daily_loss": 100.0}}, worker_id=1, initial_cash=10_000.0)
        assert settings is not None
        config, max_position_value = settings
        assert max_position_value == 2000.0
        assert "max_daily_loss" not in config  # params.risk 里的键不透传

    def test_fallback_position_pct_to_value(self):
        """表行：max_position_pct（比例）× initial_cash 换算金额"""
        row = _row(max_position_pct=0.1)
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            config, max_position_value = resolve_risk_settings({}, worker_id=1, initial_cash=10_000.0)
        assert max_position_value == 1000.0
        # 单笔订单名义额上限对齐仓位上限（引擎默认 5 万对大账户会误拒）
        assert config["max_order_value"] == 1000.0

    def test_fallback_pct_and_size_take_stricter(self):
        """仓位绝对金额与比例换算值并存时取更严（更小）者"""
        row = _row(max_position_pct=0.5, max_position_size=2000.0)
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            _, max_position_value = resolve_risk_settings({}, worker_id=1, initial_cash=10_000.0)
        assert max_position_value == 2000.0  # 0.5×10_000=5000 vs 2000 → 取 2000

    def test_fallback_daily_loss_amount_over_ratio(self):
        """亏损限额：绝对金额优先于比例字段"""
        row = _row(daily_loss_amount=800.0, daily_loss_limit=0.05)
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            config, max_position_value = resolve_risk_settings({}, worker_id=1, initial_cash=10_000.0)
        assert config["max_daily_loss"] == 800.0
        assert max_position_value is None

    def test_fallback_daily_loss_ratio_to_value(self):
        """亏损限额仅有比例字段时按 initial_cash 换算为金额"""
        row = _row(daily_loss_limit=0.05)
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            config, _ = resolve_risk_settings({}, worker_id=1, initial_cash=10_000.0)
        assert config["max_daily_loss"] == 500.0

    def test_fallback_empty_row_uses_engine_defaults(self):
        """语义变更：enabled 行字段全空 → 返回 ({}, None) 装配引擎默认档（不再视为未配置）"""
        row = _row()
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            assert resolve_risk_settings({}, worker_id=1, initial_cash=10_000.0) == ({}, None)

    def test_fallback_engine_hotfill_keys(self):
        """引擎热更新增三键映射：drawdown/leverage 原样，cooldown=0（合法值）保留"""
        row = _row(max_drawdown=0.3, max_leverage=10.0, circuit_breaker_cooldown_secs=0)
        with patch("worker.risk_config._load_risk_control_row", return_value=row):
            config, _ = resolve_risk_settings({}, worker_id=1, initial_cash=10_000.0)
        assert config["max_drawdown"] == 0.3
        assert config["max_leverage"] == 10.0
        assert config["circuit_breaker_cooldown_secs"] == 0


class TestApplyRiskConfig:
    def test_unset_skips_driver(self):
        """未配置时不得碰 driver（opt-in 语义：行为不变）"""
        driver = MagicMock()
        with patch("worker.risk_config.resolve_risk_settings", return_value=None):
            apply_risk_config(driver, {}, worker_id=1, initial_cash=10_000.0)
        driver.set_risk_config.assert_not_called()

    def test_configured_calls_driver(self):
        """配置后调用 driver.set_risk_config，参数按 resolve 结果透传"""
        driver = MagicMock()
        settings = ({"max_daily_loss": 100.0}, 5000.0)
        with patch("worker.risk_config.resolve_risk_settings", return_value=settings):
            apply_risk_config(driver, {}, worker_id=1, initial_cash=10_000.0)
        driver.set_risk_config.assert_called_once_with({"max_daily_loss": 100.0}, max_position_value=5000.0)


def test_load_row_swallows_db_error():
    """DB 访问异常 → 视为未配置返回 None（fallback 尽力而为，不阻断启动）"""
    with patch("utils.db_session.get_db_session", side_effect=RuntimeError("db down")):
        assert _load_risk_control_row(worker_id=1) is None


class TestRiskPnlFeeder:
    """当日盈亏增量换算 + 跨日清零（引擎 update_daily_pnl 是累加语义）。"""

    def test_paper_first_observation_establishes_baseline(self):
        """paper：首个权益作为当日基线，不产生盈亏回灌"""
        driver = MagicMock()
        feeder = RiskPnlFeeder(driver, daily_scoped=False)
        feeder.feed(10_000.0)
        driver.update_risk_pnl.assert_not_called()

    def test_paper_feeds_equity_delta(self):
        """paper：权益差值按增量回灌（第二次起）"""
        driver = MagicMock()
        feeder = RiskPnlFeeder(driver, daily_scoped=False)
        feeder.feed(10_000.0)
        feeder.feed(9_700.0)
        feeder.feed(9_800.0)
        assert [c.args[0] for c in driver.update_risk_pnl.call_args_list] == [-300.0, 100.0]

    def test_live_feeds_full_daily_value_on_start(self):
        """live：DB 当日已实现盈亏首次即全量回灌（重启不重置当日亏损额度）"""
        driver = MagicMock()
        feeder = RiskPnlFeeder(driver, daily_scoped=True)
        feeder.feed(-800.0)
        driver.update_risk_pnl.assert_called_once_with(-800.0)

    def test_live_feeds_increment_after_first(self):
        """live：后续按当日累计值增量回灌"""
        driver = MagicMock()
        feeder = RiskPnlFeeder(driver, daily_scoped=True)
        feeder.feed(-800.0)
        feeder.feed(-500.0)
        assert [c.args[0] for c in driver.update_risk_pnl.call_args_list] == [-800.0, 300.0]

    def test_no_call_when_value_unchanged(self):
        """观测值不变 → 不调引擎（避免无效加锁）"""
        driver = MagicMock()
        feeder = RiskPnlFeeder(driver, daily_scoped=True)
        feeder.feed(-100.0)
        feeder.feed(-100.0)
        driver.update_risk_pnl.assert_called_once_with(-100.0)

    def test_reset_if_new_day_same_day_is_noop(self):
        driver = MagicMock()
        feeder = RiskPnlFeeder(driver, daily_scoped=True)
        assert feeder.reset_if_new_day() is False
        driver.reset_risk_daily.assert_not_called()

    def test_day_roll_resets_and_rebases_paper(self):
        """paper 跨日：清零引擎当日盈亏与熔断器，权益基线取当日首个观测"""
        driver = MagicMock()
        with patch.object(risk_config_module, "_local_today", return_value=date(2026, 10, 26)):
            feeder = RiskPnlFeeder(driver, daily_scoped=False)
            feeder.feed(10_000.0)
            feeder.feed(9_500.0)  # 当日 -500
        with patch.object(risk_config_module, "_local_today", return_value=date(2026, 10, 27)):
            # 跨日后首次观测：基线取 9_500，当日盈亏重新从 0 起算
            feeder.feed(9_500.0)
            feeder.feed(9_400.0)
        driver.reset_risk_daily.assert_called_once()
        assert [c.args[0] for c in driver.update_risk_pnl.call_args_list] == [-500.0, -100.0]

    def test_day_roll_rebases_live_to_zero(self):
        """live 跨日：DB 当日累计天然从 0 起算，跨日首值按 0 基线全量回灌"""
        driver = MagicMock()
        with patch.object(risk_config_module, "_local_today", return_value=date(2026, 10, 26)):
            feeder = RiskPnlFeeder(driver, daily_scoped=True)
            feeder.feed(-1_000.0)
        with patch.object(risk_config_module, "_local_today", return_value=date(2026, 10, 27)):
            feeder.feed(-200.0)  # 新的一天，DB 当日汇总 -200
        driver.reset_risk_daily.assert_called_once()
        assert [c.args[0] for c in driver.update_risk_pnl.call_args_list] == [-1_000.0, -200.0]

    def test_reset_each_day_precedes_feed(self):
        """feed 内部先做日切检查：跨日后的首值不会按昨日基线算出错值"""
        driver = MagicMock()
        with patch.object(risk_config_module, "_local_today", return_value=date(2026, 10, 26)):
            feeder = RiskPnlFeeder(driver, daily_scoped=True)
            feeder.feed(-5_000.0)
        with patch.object(risk_config_module, "_local_today", return_value=date(2026, 10, 27)):
            feeder.feed(-10.0)
        # 若按昨日基线算，会回灌 -10-(-5000)=+4990 的错误盈利
        assert [c.args[0] for c in driver.update_risk_pnl.call_args_list] == [-5_000.0, -10.0]
        driver.reset_risk_daily.assert_called_once()
