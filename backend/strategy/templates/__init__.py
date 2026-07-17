"""8 模板都需要 @register 装饰器才能被 loader 找到。"""
from strategy.templates.dual_ma import DualMA
from strategy.templates.trend_follow import TrendFollow
from strategy.templates.grid import Grid
from strategy.templates.mean_reversion import MeanReversion
from strategy.templates.momentum import Momentum
from strategy.templates.funding_arbitrage import FundingArbitrage
from strategy.templates.cross_sectional import CrossSectional
from strategy.templates.mean_reversion_rl import MeanReversionRL
from strategy.loader import register


register("dual_ma")(DualMA)
register("trend_follow")(TrendFollow)
register("grid")(Grid)
register("mean_reversion")(MeanReversion)
register("momentum")(Momentum)
register("funding_arbitrage")(FundingArbitrage)
register("cross_sectional")(CrossSectional)
register("mean_reversion_rl")(MeanReversionRL)
