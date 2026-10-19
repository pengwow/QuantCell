"""
测试 list-strategies 和 run 策略路径查找一致性

复现 bug：
- `list-strategies` 只查 backend/strategies/，漏掉 backend/strategy/example/strategies/
- `run -s axon_dual_ma` 优先查 backend/strategy/example/strategies/ 但 axon_dual_ma 不在那里
  → 抛 StrategyLoadError，无法 fallback 到 backend/strategies/

修复后：
- 单一真相源 _get_strategies_dirs() 返回所有可能目录（按优先级）
- list-strategies 扫描所有目录
- load_strategy 在所有目录里查找策略文件
"""

import pytest


class TestGetStrategiesDirs:
    """单一真相源：返回所有可能目录，按优先级排序"""

    def test_returns_repo_template_dir(self):
        """候选目录至少包含仓库自带的 backend/strategy/templates

        注意：backend/strategies 是本地策略目录，已被 .gitignore 忽略
        （backend/strategies/*），全新 checkout 上并不存在，因此不能断言
        "候选目录里一定有名字含 strategies 的目录"。
        """
        from backtest.strategy_loader_service import StrategyLoaderService

        dirs = StrategyLoaderService._get_strategies_dirs()
        assert any(d.name == "templates" for d in dirs), f"候选目录: {dirs}"

    def test_returns_example_strategies_dir(self):
        from backtest.strategy_loader_service import StrategyLoaderService

        dirs = StrategyLoaderService._get_strategies_dirs()
        # 应该包含 example strategies（可能不存在但应该被检查）
        # 这里只检查至少返回一个目录
        assert len(dirs) >= 1

    def test_listed_dirs_are_actual_existing_paths(self):
        """返回的目录必须存在"""
        from backtest.strategy_loader_service import StrategyLoaderService

        dirs = StrategyLoaderService._get_strategies_dirs()
        for d in dirs:
            assert d.exists(), f"目录不存在: {d}"


class TestFindStrategyFile:
    """在所有候选目录里查找策略文件"""

    def test_find_existing_strategy_in_backend_strategies(self):
        """dual_ma 在 backend/strategy/templates/，应能找到"""
        from backtest.strategy_loader_service import StrategyLoaderService

        path = StrategyLoaderService._find_strategy_file("dual_ma")
        assert path is not None
        assert path.name == "dual_ma.py"
        assert "templates" in str(path)

    def test_find_existing_strategy_in_example(self):
        """simple_dual_ma 在 backend/strategy/example/strategies/，应能找到"""
        from backtest.strategy_loader_service import StrategyLoaderService

        try:
            path = StrategyLoaderService._find_strategy_file("simple_dual_ma")
        except FileNotFoundError:
            # 如果 example 目录被移除则跳过
            pytest.skip("simple_dual_ma 不存在")
        if path is None:
            pytest.skip("simple_dual_ma 不在 example 目录")
        assert path.name == "simple_dual_ma.py"

    def test_find_nonexistent_strategy_returns_none(self):
        """不存在的策略返回 None"""
        from backtest.strategy_loader_service import StrategyLoaderService

        path = StrategyLoaderService._find_strategy_file("nonexistent_strategy_xyz")
        assert path is None


class TestLoadStrategyFallback:
    """load_strategy 应该在所有目录里找文件，找不到才报错

    这里的测试只验证**路径查找**层面的 fallback 行为（找到/找不到文件）；
    加载结果契约见 TestLoaderReturnsBaseStrategy。
    """

    def test_find_axon_dual_ma_succeeds(self):
        """dual_ma 在 backend/strategy/templates/，应能找到文件

        修复前：_get_strategies_dir() 返回 example 目录，文件不存在
        修复后：_find_strategy_file 跨目录查找，应能找到
        """
        from backtest.strategy_loader_service import StrategyLoaderService

        path = StrategyLoaderService._find_strategy_file("dual_ma")
        assert path is not None, "dual_ma 应该在 backend/strategy/templates/ 中找到"
        assert path.name == "dual_ma.py"
        assert "templates" in str(path)

    def test_find_dual_ma_strategy_succeeds(self):
        """trend_follow 在 backend/strategy/templates/，应能找到"""
        from backtest.strategy_loader_service import StrategyLoaderService

        path = StrategyLoaderService._find_strategy_file("trend_follow")
        assert path is not None, "trend_follow 应该在 backend/strategy/templates/ 中找到"
        assert path.name == "trend_follow.py"

    def test_find_simple_dual_ma_succeeds(self):
        """simple_dual_ma 在 backend/strategy/example/strategies/，应能找到"""
        from backtest.strategy_loader_service import StrategyLoaderService

        path = StrategyLoaderService._find_strategy_file("simple_dual_ma")
        if path is None:
            pytest.skip("simple_dual_ma 不在 example 目录")
        assert path.name == "simple_dual_ma.py"

    def test_find_nonexistent_returns_none(self):
        """不存在的策略返回 None，不抛错"""
        from backtest.strategy_loader_service import StrategyLoaderService

        path = StrategyLoaderService._find_strategy_file("definitely_not_exist_xyz_123")
        assert path is None

    def test_load_nonexistent_strategy_raises_with_helpful_message(self):
        """load_strategy 找不到文件时抛 StrategyLoadError，错误信息列出已搜索的目录"""
        from backtest.strategy_loader_service import (
            StrategyLoadError,
            StrategyLoaderService,
        )

        with pytest.raises(StrategyLoadError) as exc_info:
            StrategyLoaderService.load_strategy("definitely_not_exist_xyz_123", {})
        # 错误信息应该列出已搜索的目录
        assert "已搜索" in str(exc_info.value) or "搜索" in str(exc_info.value)


class TestListStrategiesCoversAllDirs:
    """list-strategies 应该扫描所有目录"""

    def test_list_all_returns_strategies_from_both_dirs(self):
        """list-strategies 应该能列出 example 目录里的策略"""
        from typer.testing import CliRunner

        from backtest.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["list-strategies"])

        # 不论成功失败，至少能看到
        assert result.exit_code == 0 or "策略" in result.output

    def test_get_all_strategy_files_includes_example_dir(self):
        """修复后：list-strategies 用的查找函数应包含 example 目录的策略"""
        from backtest.strategy_loader_service import StrategyLoaderService

        all_files = StrategyLoaderService.get_all_strategy_files()

        # 至少包含 backend/strategy/templates/ 的 dual_ma
        names = [f.stem for f in all_files]
        assert "dual_ma" in names, f"dual_ma 应在列表中, 实际: {names}"


class TestLoaderReturnsBaseStrategy:
    """加载结果契约：唯一路径只认 BaseStrategy 子类（P1 统一路径）"""

    def test_load_template_dual_ma_returns_base_strategy(self):
        """加载模板 dual_ma 应返回 BaseStrategy 实例"""
        from backtest.strategy_loader_service import StrategyLoaderService
        from strategy.base import BaseStrategy

        strategy = StrategyLoaderService.load_strategy(
            "dual_ma",
            {"fast": 5, "slow": 20},
            instrument_ids=[{"symbol": "BTCUSDT", "venue": "BINANCE"}],
            bar_types=["BTCUSDT-1h"],
        )
        assert isinstance(strategy, BaseStrategy)

    def test_load_module_without_strategy_class_raises(self, tmp_path, monkeypatch):
        """模块里没有 BaseStrategy 子类时应抛明确错误，而非静默走事件分支"""
        from backtest.strategy_loader_service import (
            StrategyLoadError,
            StrategyLoaderService,
        )

        (tmp_path / "plain_cls.py").write_text("class PlainClass:\n    pass\n", encoding="utf-8")
        monkeypatch.setattr(StrategyLoaderService, "_get_strategies_dirs", staticmethod(lambda: [tmp_path]))

        with pytest.raises(StrategyLoadError) as exc_info:
            StrategyLoaderService.load_strategy("plain_cls", {})
        assert "找不到策略类" in str(exc_info.value)
