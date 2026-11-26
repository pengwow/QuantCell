"""账户快照端点纯函数检查（无网络）：归一化与估值的边界行为"""

import collector.api.exchanges as mod


def test_norm_order_strips_settlement_and_coerces():
    o = mod._norm_order(
        {
            "id": "1",
            "timestamp": 123,
            "symbol": "BTC/USDT:USDT",
            "type": "market",
            "side": "buy",
            "price": "100",
            "amount": "2",
            "filled": 1,
            "status": "closed",
        }
    )
    assert o["pair"] == "BTC/USDT" and o["qty"] == 2.0 and o["type"] == "market"


def test_norm_position_skips_empty_and_core_fields():
    assert mod._norm_position({"contracts": 0}) is None
    p = mod._norm_position(
        {
            "contracts": "0.5",
            "symbol": "ETH/USDT:USDT",
            "side": "short",
            "marginMode": "isolated",
            "leverage": "5",
            "entryPrice": "3200",
            "markPrice": "3100",
            "notional": "-310",
            "unrealizedPnl": "20",
            "initialMargin": "62",
            "maintenanceMargin": "6.2",
            "liquidationPrice": "3480",
        }
    )
    assert p is not None
    # 实盘字段齐全时逐项透出；marginRatio 无值置 0（前端显示 —）
    assert p["qty"] == 0.5 and p["leverage"] == 5.0 and p["notional"] == 310.0
    assert p["maintMargin"] == 6.2 and p["liqPrice"] == 3480.0 and p["marginRatio"] == 0.0


def test_balance_rows_valuation_and_quote_price_one():
    prices = {"BTC": 96000.0}
    rows = mod._balance_rows(
        {"free": {"BTC": 1.0, "USDT": 100.0}, "used": {"BTC": 1.0, "USDT": 50.0}, "total": {"BTC": 2.0, "USDT": 150.0}},
        "USDT",
        prices,
    )
    by_ccy = {r["currency"]: r for r in rows}
    assert by_ccy["BTC"]["valueUsdt"] == 192_000.0
    assert by_ccy["USDT"]["priceUsdt"] == 1.0 and by_ccy["USDT"]["valueUsdt"] == 150.0
    assert rows[0]["currency"] == "BTC"  # 按估值降序


def test_futures_totals_reads_raw_info():
    t = mod._futures_account_totals(
        {
            "info": {
                "totalWalletBalance": "100",
                "totalUnrealizedProfit": "5",
                "totalMarginBalance": "105",
                "availableBalance": "80",
                "totalInitialMargin": "25",
            }
        }
    )
    assert t == {
        "walletUsdt": 100.0,
        "unrealizedUsdt": 5.0,
        "equityUsdt": 105.0,
        "availableUsdt": 80.0,
        "usedUsdt": 25.0,
    }
    assert mod._futures_account_totals({"info": {}}) is None


def test_resolve_credentials_by_env():
    cfg = {"live_api_key": "L", "api_key": "legacy", "testnet_api_key": "T"}
    assert mod._resolve_credentials(cfg, "live")[0] == "L"
    assert mod._resolve_credentials({}, "live")[0] == ""  # 无 live 密钥不得回退拿 testnet
    assert mod._resolve_credentials(cfg, "testnet")[0] == "T"


def test_norm_trading_mode_three_ways():
    """spot/futures/margin 三档；margin 不得被吞成 spot（杠杆钱包口径）"""
    assert mod._norm_trading_mode("spot") == "spot"
    assert mod._norm_trading_mode("future") == "future"
    assert mod._norm_trading_mode("futures") == "future"
    assert mod._norm_trading_mode("margin") == "margin"
    assert mod._norm_trading_mode("MARGIN") == "margin"
    assert mod._norm_trading_mode("junk") == "spot"


def test_snapshot_cache_hit_and_refresh(monkeypatch):
    """命中缓存秒回（fetchedAt 为旧值）；refresh=1 绕过缓存强拉；空态不写缓存"""
    mod._SNAPSHOT_CACHE.clear()
    mod._ACTIVE_KEYS.clear()

    calls = {"n": 0}

    def fake_build(exchange_id, eff_env):
        calls["n"] += 1
        return {"configured": True, "fetchedAt": 1000 * calls["n"], "exchange": exchange_id, "env": eff_env}

    monkeypatch.setattr(mod, "_build_snapshot", fake_build)

    first = mod.get_exchange_account_snapshot("binance", "testnet").data
    assert calls["n"] == 1 and first["fetchedAt"] == 1000
    assert mod._SNAPSHOT_CACHE[("binance", "testnet")]["configured"] is True

    # 二次请求：命中缓存，不触发拉取，fetchedAt 仍为旧值
    second = mod.get_exchange_account_snapshot("binance", "testnet").data
    assert calls["n"] == 1 and second["fetchedAt"] == 1000
    assert mod._ACTIVE_KEYS == {("binance", "testnet")}

    # refresh=1：强制拉新，缓存同步更新
    third = mod.get_exchange_account_snapshot("binance", "testnet", refresh=True).data
    assert calls["n"] == 2 and third["fetchedAt"] == 2000
    assert mod._SNAPSHOT_CACHE[("binance", "testnet")]["fetchedAt"] == 2000


def test_snapshot_empty_state_not_cached(monkeypatch):
    """paper 空态响应即时、不写缓存"""
    mod._SNAPSHOT_CACHE.clear()
    monkeypatch.setattr(
        mod,
        "SystemConfigBusiness",
        type(
            "SB",
            (),
            {"get_all_flattened_by_prefix": staticmethod(lambda p: {"binance": {"trading_environment": "paper"}})},
        ),
    )
    mod.get_exchange_account_snapshot("binance")
    assert ("binance", "paper") not in mod._SNAPSHOT_CACHE
    assert mod.get_exchange_account_snapshot("binance").data["configured"] is False
    mod._SNAPSHOT_CACHE.clear()


def test_norm_position_demo_v3_fallbacks():
    """币安 demo v3 positionRisk 无 leverage/maintMargin：杠杆推算、维持保证金分摊、两平价/保证金比率透出"""
    p = {  # 模拟 demo v3 原始解析结果：leverage/maintMargin 均缺
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "marginMode": "cross",
        "contracts": 2.344,
        "entryPrice": 1706.33,
        "markPrice": 1700.0,
        "notional": 3976.63,
        "initialMargin": 795.33,  # 3976.63/795.33 = 5x
        "liquidationPrice": 103.65,
        "marginRatio": 0.0053,
        "unrealizedPnl": -23.0,
        "info": {"breakEvenPrice": "1707.01", "unRealizedProfit": "-23.0"},
    }
    row = mod._norm_position(p, maint_share=19.87)
    assert row and row["leverage"] == 5.0  # 保证金占用推算
    assert row["maintMargin"] == 19.87  # 账户级分摊兜底
    assert row["breakeven"] == 1707.01 and row["marginRatio"] == 0.53
    # 显式 leverage 优先于推算（实盘 v2/真实账户有值）
    p["leverage"] = 3
    assert mod._norm_position(p)["leverage"] == 3.0
