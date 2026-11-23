"""采集页品种选项必须透传自选组标识色。

前端标的下拉（回测配置 / Worker 弹窗）用 `pool.color` 画组色圆点，与数据管理页
自选组保持一致。这个字段一旦在 `/data-pools/collection/symbols` 被漏掉，
下拉里所有组都会回落成同一个默认色——UI 看着正常但颜色语义丢失，故留断言守住。
"""

from unittest.mock import MagicMock, patch

from collector.api.data_pool import get_collection_symbols
from collector.schemas_data_pool import CollectionSymbolPool


def test_pool_schema_color_is_optional():
    """显式给色原样保留；不给时为 None（前端据此回落默认色）。"""
    assert CollectionSymbolPool(id=1, name="自选", color="#722ed1", symbols=[]).color == "#722ed1"
    assert CollectionSymbolPool(id=2, name="自选", symbols=[]).color is None


def test_collection_symbols_returns_pool_color():
    """端到端透传：DataPool 行里的 color 必须出现在响应里。"""
    pool_rows = [
        {"id": 1, "name": "热门货币对", "color": "#1890ff"},
        {"id": 2, "name": "未设色的组", "color": None},
    ]
    db = MagicMock()
    db.query.return_value.filter_by.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.all.return_value = []

    with (
        patch("collector.api.data_pool.DataPool.get_all", return_value=pool_rows),
        patch("collector.api.data_pool.DataPool.get_assets", return_value=["BTC/USDT"]),
        patch("collector.db.database.SessionLocal", return_value=db),
        patch("collector.db.database.init_database_config"),
    ):
        res = get_collection_symbols(type=None, exchange=None)

    pools = res.data.data_pools
    assert [p.id for p in pools] == [1, 2]
    assert pools[0].color == "#1890ff"
    assert pools[1].color is None
    assert pools[0].symbols == ["BTC/USDT"]
