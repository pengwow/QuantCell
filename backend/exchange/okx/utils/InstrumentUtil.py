import math
import time
import httpx
from decimal import Decimal

from okx.PublicData import PublicAPI

from okx_market_maker import instruments
from okx_market_maker.position_management_service.model.Positions import Position
from okx_market_maker.settings import IS_PAPER_TRADING, PROXY
from okx_market_maker.utils.OkxEnum import InstType, OrderSide, InstState
from okx_market_maker.market_data_service.model.Instrument import Instrument
from okx_market_maker import mark_px_container


INST_ID_SUGGESTION = "valid instId examples:\n"\
                     "SPOT: BTC-USDT, SWAP: BTC-USDT-SWAP, FUTURES: BTC_USDT-230630, "\
                     f"OPTION: BTC-USDT-230630-30000-C."


class InstrumentUtil:
    public_api = PublicAPI(flag='0' if not IS_PAPER_TRADING else '1', proxy=PROXY or None)

    @classmethod
    def get_inst_type_from_inst_id(cls, inst_id: str) -> InstType:
        inst_id_parts = inst_id.split("-")
        if len(inst_id_parts) < 2 or len(inst_id_parts) > 5 or len(inst_id_parts) == 4:
            raise ValueError(f"Invalid InstId {inst_id}, {INST_ID_SUGGESTION}")
        if len(inst_id_parts) == 2:
            return InstType.SPOT
        if len(inst_id_parts) == 3:
            if inst_id_parts[2] == "SWAP":
                return InstType.SWAP
            else:
                return InstType.FUTURES
        if len(inst_id_parts) == 5:
            return InstType.OPTION

    @classmethod
    def get_instrument(cls, inst_id: str, query_inst_type: InstType = None) -> Instrument:
        """
        获取指定交易对的Instrument对象，包含交易规则和参数
        
        参数：
            inst_id (str): 交易对ID，如"BTC-USDT"
            query_inst_type (InstType, optional): 查询的交易类型，默认为None
        
        返回值：
            Instrument: 包含交易对信息的对象
        
        异常：
            ValueError: 当交易对不存在或状态异常时
            httpx.ConnectError: 当网络连接失败且重试超过限制时
        """
        inst_type = InstrumentUtil.get_inst_type_from_inst_id(inst_id)
        if inst_type == InstType.SPOT and query_inst_type == InstType.MARGIN:
            inst_type = query_inst_type
        if f"{inst_id}:{inst_type.value}" in instruments:
            return instruments[f"{inst_id}:{inst_type.value}"]
        
        # 添加重试机制处理网络连接错误
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                uly = ''
                if inst_type == InstType.OPTION:
                    uly = inst_id.split('-')[0] + '-' + inst_id.split('-')[1]
                inst_result = cls.public_api.get_instruments(instType=inst_type.value, instId=inst_id, uly=uly)
                if inst_result.get("code") != '0':
                    raise ValueError(f"{inst_id} inst not exists in OKX: {inst_result}, {INST_ID_SUGGESTION}")
                data = inst_result["data"]
                json_response = data[0]
                instrument = Instrument.init_from_json(json_response)
                if instrument.state != InstState.LIVE:
                    raise ValueError(f"{inst_id} inst state error in OKX: {instrument.state}")
                instruments[f"{inst_id}:{inst_type.value}"] = instrument
                return instrument
            except httpx.ConnectError as e:
                retry_count += 1
                print(f"连接错误 (尝试 {retry_count}/{max_retries}): {e}")
                if retry_count >= max_retries:
                    raise  # 重试次数用尽后重新抛出异常
                time.sleep(1)  # 等待1秒后重试

    @classmethod
    def price_trim_by_tick_sz(cls, price: float, side: OrderSide, instrument: Instrument) -> str:
        if side == OrderSide.BUY:
            return (math.floor(Decimal(str(price)) / instrument.tick_sz) * instrument.tick_sz).to_eng_string()
        else:
            return (math.ceil(Decimal(str(price)) / instrument.tick_sz) * instrument.tick_sz).to_eng_string()

    @classmethod
    def quantity_trim_by_lot_sz(cls, quantity: float, instrument: Instrument) -> str:
        return (round(Decimal(str(quantity)) / instrument.lot_sz) * instrument.lot_sz).to_eng_string()

    @classmethod
    def get_asset_value_ccy(cls, instrument: Instrument, position: Position) -> str:
        if instrument.inst_type == InstType.MARGIN:
            return position.ccy
        return instrument.settle_ccy

    @classmethod
    def get_asset_exposure_ccy(cls, instrument: Instrument) -> str:
        return instrument.inst_id.split("-")[0]

    @classmethod
    def get_asset_quote_ccy(cls, instrument: Instrument) -> str:
        return instrument.inst_id.split("-")[1]

    @classmethod
    def get_instrument_mark_px(cls, inst_id: str) -> float:
        if not mark_px_container:
            return 0
        mark_px_cache = mark_px_container[0]
        mark_px = mark_px_cache.get_mark_px(inst_id)
        if not mark_px:
            return 0
        return mark_px.mark_px
