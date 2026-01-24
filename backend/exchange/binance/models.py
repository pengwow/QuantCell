import peewee
from zbot.models.candle import Candle as CandleBase
from zbot.services.db import database


class Candle(CandleBase):
    # 收盘时间
    close_time = peewee.BigIntegerField(null=True)
    # 成交额
    quote_volume = peewee.FloatField(default=0)
    # 成交笔数
    count = peewee.IntegerField(default=0)
    # 主动买入成交量
    taker_buy_volume = peewee.FloatField(default=0)
    # 主动买入成交额
    taker_buy_quote_volume = peewee.FloatField(default=0)
    # 忽略
    ignore = peewee.BooleanField(default=False)

    class Meta:
        table_name = "binance_candle"
        database = database.db
        indexes = ((("symbol", "timeframe", "open_time"), True),)


database.open_connection()
database.db.create_tables([Candle])
database.db.close()
