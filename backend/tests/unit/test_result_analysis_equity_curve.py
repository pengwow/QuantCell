# -*- coding: utf-8 -*-
"""回测结果分析模块测试 — 覆盖 equity_curve tuple/list 序列化路径

回归测试:axon 适配层产出 [(time_ns, equity), ...] 格式的 equity_curve,
旧 _serialize_equity_curve 只支持 dict,会抛 'list' object has no attribute 'items'
"""
import pytest


class TestEquityCurveSerialization:
    """equity_curve 序列化的兼容性测试"""

    def test_equity_curve_tuple_format(self):
        """axon 适配层产物：(time_ns, equity) tuple 列表 → 转 dict"""
        from backtest.result_analysis import ResultSerializer
        ser = ResultSerializer()
        # axon 适配层 backtest_loop 产出的格式
        curve = [
            (1735689600000000000, 100000.0),
            (1735689700000000000, 100100.0),
            (1735689800000000000, 99950.5),
        ]
        result = ser._serialize_equity_curve(curve)
        assert len(result) == 3
        assert result[0] == {"timestamp": 1735689600000000000, "equity": 100000.0}
        assert result[1] == {"timestamp": 1735689700000000000, "equity": 100100.0}
        assert result[2]["equity"] == 99950.5

    def test_equity_curve_list_format(self):
        """list 格式也应支持(list(t) for t in equity_curve)"""
        from backtest.result_analysis import ResultSerializer
        ser = ResultSerializer()
        curve = [[100, 1.0], [200, 2.0]]
        result = ser._serialize_equity_curve(curve)
        assert result[0] == {"timestamp": 100, "equity": 1.0}
        assert result[1] == {"timestamp": 200, "equity": 2.0}

    def test_equity_curve_dict_format_unchanged(self):
        """事件驱动引擎 dict 格式仍按原逻辑序列化"""
        from datetime import datetime
        from backtest.result_analysis import ResultSerializer
        ser = ResultSerializer()
        ts = datetime(2024, 1, 1)
        curve = [{"timestamp": ts, "equity": 100.0}]
        result = ser._serialize_equity_curve(curve)
        assert result[0]["timestamp"] == "2024-01-01T00:00:00"
        assert result[0]["equity"] == 100.0

    def test_equity_curve_empty(self):
        """空列表安全返回 []"""
        from backtest.result_analysis import ResultSerializer
        ser = ResultSerializer()
        assert ser._serialize_equity_curve([]) == []

    def test_equity_curve_short_tuple_skipped(self):
        """长度 < 2 的元组跳过(数据不完整)"""
        from backtest.result_analysis import ResultSerializer
        ser = ResultSerializer()
        curve = [(100, 1.0), (200,), (300, 3.0)]
        result = ser._serialize_equity_curve(curve)
        assert len(result) == 2
        assert result[0]["timestamp"] == 100
        assert result[1]["equity"] == 3.0

    def test_save_results_equity_curve_tuple(self):
        """端到端：含 tuple equity_curve 的 results 能成功 save 到 JSON"""
        import json
        import os
        import tempfile
        from backtest.result_analysis import save_results

        results = {
            "ETHUSDT_15m": {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "metrics": {"win_rate": 0.35, "total_pnl": -100.0},
                "trades": [],
                "positions": [],
                "equity_curve": [(100, 1.0), (200, 2.0), (300, 1.5)],
            },
            "portfolio": {
                "metrics": {"win_rate": 0.35},
                "trades": [],
                "equity_curve": [(100, 1.0), (200, 2.0)],
            },
            "account": {"starting_balance": 100000, "final_nav": 99000, "total_pnl": -1000},
            "_meta": {"engine": "axon", "strategy": "test"},
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            ok = save_results(results, tmp_path, "json")
            assert ok is True
            with open(tmp_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            assert saved["ETHUSDT_15m"]["equity_curve"][0] == {"timestamp": 100, "equity": 1.0}
            assert saved["ETHUSDT_15m"]["metrics"]["win_rate"] == 0.35
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
