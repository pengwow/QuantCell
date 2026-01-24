from okx_market_maker.utils.OkxEnum import AccountConfigMode, InstType, TdMode
from okx_market_maker.settings import TRADING_MODE


class TdModeUtil:
    @classmethod
    def decide_trading_mode(cls, account_config: AccountConfigMode, inst_type: InstType,
                            td_mode_setting: str = TRADING_MODE) -> TdMode:
        """
        交易模式，下单时需要指定交易模式。
        非保证金模式：
        - 现货和期权买方：cash（现货）
        单币种保证金账户：
        - 逐仓保证金：isolated
        - 全仓保证金：cross
        - 全仓现货：cash
        - 全仓期货/永续/期权：cross
        - 逐仓期货/永续/期权：isolated
        多币种保证金账户：
        - 逐仓保证金：isolated
        - 全仓现货：cross
        - 全仓期货/永续/期权：cross
        - 逐仓期货/永续/期权：isolated
        组合保证金：
        - 逐仓保证金：isolated
        - 全仓现货：cross
        - 全仓期货/永续/期权：cross
        - 逐仓期货/永续/期权：isolated
        :param account_config: 账户配置模式
        :param inst_type: 产品类型
        :param td_mode_setting: 交易模式设置
        :return: 交易模式枚举值
        """
        if account_config == AccountConfigMode.CASH:
            if inst_type not in [InstType.SPOT, InstType.OPTION]:
                raise ValueError(f"Invalid inst type {inst_type} in Cash Mode!")
            return TdMode.CASH
        if account_config == AccountConfigMode.SINGLE_CCY_MARGIN:
            if td_mode_setting in TdMode:
                assigned_trading_mode = TdMode(td_mode_setting)
                if inst_type not in [InstType.SPOT, InstType.MARGIN] and assigned_trading_mode == TdMode.CASH:
                    return TdMode.CROSS
                if inst_type == InstType.SPOT:
                    return TdMode.CASH
                return assigned_trading_mode
            if inst_type == InstType.SPOT:
                return TdMode.CASH
            return TdMode.CROSS
        if account_config in [AccountConfigMode.MULTI_CCY_MARGIN, AccountConfigMode.PORTFOLIO_MARGIN]:
            if td_mode_setting in TdMode:
                assigned_trading_mode = TdMode(td_mode_setting)
                if assigned_trading_mode == TdMode.CASH:
                    return TdMode.CROSS
                if inst_type == InstType.MARGIN:
                    return TdMode.ISOLATED
                if inst_type == InstType.SPOT:
                    return TdMode.CROSS
                return assigned_trading_mode
            if inst_type == InstType.MARGIN:
                return TdMode.ISOLATED
            return TdMode.CROSS
        raise ValueError(f"Invalid Account config mode {account_config}!")
