import asyncio
import time
import traceback
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Dict, Tuple
import logging
from copy import deepcopy
import httpx

from okx.Status import StatusAPI
from okx_market_maker.market_data_service.model.Instrument import Instrument, InstState
from okx_market_maker.market_data_service.model.Tickers import Tickers
from okx_market_maker.position_management_service.model.Positions import Positions
from okx_market_maker.strategy.params.ParamsLoader import ParamsLoader
from okx_market_maker.utils.InstrumentUtil import InstrumentUtil
from okx_market_maker.order_management_service.model.OrderRequest import PlaceOrderRequest, \
    AmendOrderRequest, CancelOrderRequest
from okx.Trade import TradeAPI
from okx.Account import AccountAPI
from okx_market_maker.settings import *
from okx_market_maker import orders_container, order_books, account_container, positions_container, tickers_container, \
    mark_px_container
from okx_market_maker.strategy.model.StrategyOrder import StrategyOrder, StrategyOrderStatus
from okx_market_maker.strategy.model.StrategyMeasurement import StrategyMeasurement
from okx_market_maker.market_data_service.model.OrderBook import OrderBook
from okx_market_maker.position_management_service.model.Account import Account
from okx_market_maker.order_management_service.model.Order import Orders, Order, OrderState, OrderSide
from okx_market_maker.strategy.risk.RiskCalculator import RiskCalculator
from okx_market_maker.market_data_service.WssMarketDataService import WssMarketDataService
from okx_market_maker.order_management_service.WssOrderManagementService import WssOrderManagementService
from okx_market_maker.position_management_service.WssPositionManagementService import WssPositionManagementService
from okx_market_maker.market_data_service.RESTMarketDataService import RESTMarketDataService
from okx_market_maker.utils.OkxEnum import AccountConfigMode, TdMode, InstType
from okx_market_maker.utils.TdModeUtil import TdModeUtil


class BaseStrategy(ABC):
    """
    做市策略抽象基类，定义了量化做市商的核心框架和标准接口
    所有具体做市策略（如网格做市、套利做市等）都应继承此类并实现抽象方法
    
    在加密货币做市中，基类负责：
    1. 核心服务初始化（市场数据、订单管理、仓位管理）
    2. 订单生命周期管理（下单、改单、撤单）
    3. 策略订单缓存与状态跟踪
    4. 市场数据与账户信息获取
    
    子类需实现order_operation_decision方法来定义具体的做单逻辑
    """
    trade_api: TradeAPI  # OKX交易API客户端，用于下单、改单、撤单等操作
    status_api: StatusAPI  # OKX状态API客户端，用于查询系统状态

    instrument: Instrument  # 交易标的工具信息对象
    trading_instrument_type: InstType  # 交易标的类型（如SPOT现货、SWAP永续合约等）
    _strategy_order_dict: Dict[str, StrategyOrder]  # 策略订单缓存字典，key为客户端订单ID，value为策略订单对象
    _strategy_measurement: StrategyMeasurement  # 策略绩效测量对象，用于计算盈亏等指标
    _account_mode: AccountConfigMode = None  # 账户配置模式（如简单账户、单币种保证金账户等）

    def __init__(self, api_key=API_KEY, api_key_secret=API_KEY_SECRET, api_passphrase=API_PASSPHRASE,
                 is_paper_trading: bool = IS_PAPER_TRADING, proxy: str = PROXY):
        """
        初始化做市策略基类实例，创建与OKX交易所的连接并初始化核心服务
        
        在加密货币量化交易中，初始化过程非常重要，它建立了与交易所的通信通道
        并准备好做市所需的所有基础组件。此构造函数完成以下关键工作：
        1. 创建交易、状态和账户API客户端
        2. 初始化市场数据服务(WSS实时行情)、订单管理服务和仓位管理服务
        3. 初始化策略订单缓存字典和参数加载器
        
        :param api_key: OKX API密钥
        :param api_key_secret: OKX API密钥密钥
        :param api_passphrase: OKX API密码
        :param is_paper_trading: 是否为模拟交易环境（True为模拟盘，False为实盘）
        """
        # 创建OKX交易API客户端，flag参数控制实盘(0)或模拟盘(1)
        self.trade_api = TradeAPI(api_key=api_key, api_secret_key=api_key_secret, passphrase=api_passphrase,
                                  flag='0' if not is_paper_trading else '1', debug=False, proxy=proxy or None)
        # 创建OKX状态API客户端
        self.status_api = StatusAPI(flag='0' if not is_paper_trading else '1', debug=False, proxy=proxy or None)
        # 创建OKX账户API客户端
        self.account_api = AccountAPI(api_key=api_key, api_secret_key=api_key_secret, passphrase=api_passphrase,
                                      flag='0' if not is_paper_trading else '1', debug=False, proxy=proxy or None)
        
        # 解析代理配置
        proxy_host, proxy_port, proxy_type = None, None, None
        if proxy:
            if proxy.startswith("http://"):
                proxy_type = "http"
                proxy = proxy[7:]
            elif proxy.startswith("socks5://"):
                proxy_type = "socks5"
                proxy = proxy[9:]
            if ":" in proxy:
                proxy_host, proxy_port = proxy.split(":")
                proxy_port = int(proxy_port)
        
        # 初始化Websocket市场数据服务，订阅订单簿频道
        self.mds = WssMarketDataService(
            url="wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999" if is_paper_trading
            else "wss://wspap.okx.com:8443/ws/v5/public",
            inst_id=TRADING_INSTRUMENT_ID,
            channel="books",
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_type=proxy_type
        )
        # 初始化REST市场数据服务，用于获取历史数据
        self.rest_mds = RESTMarketDataService(is_paper_trading)
        # 初始化Websocket订单管理服务，用于接收订单状态更新
        self.oms = WssOrderManagementService(
            url="wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999" if is_paper_trading
            else "wss://wspap.okx.com:8443/ws/v5/private",
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_type=proxy_type)
        # 初始化Websocket仓位管理服务，用于接收仓位变动通知
        self.pms = WssPositionManagementService(
            url="wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999" if is_paper_trading
            else "wss://wspap.okx.com:8443/ws/v5/private",
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_type=proxy_type)
        # 初始化策略订单字典，用于缓存和跟踪所有策略生成的订单
        self._strategy_order_dict = dict()
        # 初始化参数加载器，用于加载策略参数配置
        self.params_loader = ParamsLoader()

    @abstractmethod
    def order_operation_decision(self) -> \
            Tuple[List[PlaceOrderRequest], List[AmendOrderRequest], List[CancelOrderRequest]]:
        """
        做市策略核心决策方法（抽象方法），子类必须实现具体逻辑
        
        在加密货币做市中，此方法决定了做市商的核心行为：
        1. 根据市场行情（如订单簿、最新成交价）决定新订单的价格和数量
        2. 根据市场变化决定是否需要修改现有挂单（如价格偏移调整）
        3. 根据风险控制规则决定是否需要撤销现有订单
        
        典型的做市逻辑包括：
        - 网格做市：在基准价上下设置一系列等间隔的买单和卖单
        - 盘口跟随：根据最佳买卖价设置挂单价格
        - 波动率调整：根据市场波动动态调整报价价差
        
        :return: 包含三个列表的元组：
                 1. 需要下单的请求列表
                 2. 需要修改的订单请求列表
                 3. 需要撤销的订单请求列表
        """
        pass

    def get_strategy_orders(self) -> Dict[str, StrategyOrder]:
        """
        获取当前所有策略订单的副本，防止外部直接修改内部缓存
        
        在做市过程中，策略订单缓存是核心数据结构，记录了所有由策略生成的订单状态
        此方法返回副本而非原始字典，遵循了保护性拷贝原则，确保策略内部状态安全
        
        :return: 策略订单字典的深拷贝，key为客户端订单ID，value为StrategyOrder对象
        """
        return self._strategy_order_dict.copy()

    def get_bid_strategy_orders(self) -> List[StrategyOrder]:
        """
        获取所有买入策略订单并按价格降序排序
        
        在加密货币做市中，买单（Bid）通常挂在当前市场价格下方，形成买入盘口
        按价格降序排序后，列表第一个元素是最高价格的买单（最接近市场价格）
        这种排序有助于：
        1. 快速找到最优买单位置
        2. 计算买单深度分布
        3. 决定是否需要在更高价位补充买单以提高成交概率
        
        :return: 按价格从高到低排序的买入策略订单列表
        """
        buy_orders = list()
        for cid, strategy_order in self._strategy_order_dict.items():
            if strategy_order.side == OrderSide.BUY:
                buy_orders.append(strategy_order)
        return sorted(buy_orders, key=lambda x: float(x.price), reverse=True)

    def get_ask_strategy_orders(self) -> List[StrategyOrder]:
        """
        获取所有卖出策略订单并按价格升序排序
        
        在加密货币做市中，卖单（Ask）通常挂在当前市场价格上方，形成卖出盘口
        按价格升序排序后，列表第一个元素是最低价格的卖单（最接近市场价格）
        这种排序有助于：
        1. 快速找到最优卖单位置
        2. 计算卖单深度分布
        3. 决定是否需要在更低价位补充卖单以提高成交概率
        
        :return: 按价格从低到高排序的卖出策略订单列表
        """
        sell_orders = list()
        for cid, strategy_order in self._strategy_order_dict.items():
            if strategy_order.side == OrderSide.SELL:
                sell_orders.append(strategy_order)
        return sorted(sell_orders, key=lambda x: float(x.price), reverse=False)

    def place_orders(self, order_request_list: List[PlaceOrderRequest]):
        """
        批量下单并缓存策略订单，遵循OKX API限制（每次最多20个订单）
        
        在加密货币做市中，批量下单是提高效率的关键：
        1. 减少API调用次数，降低网络延迟影响
        2. 确保订单批次一致性，避免部分订单因时序问题导致的价格偏差
        3. 便于统一管理订单状态和错误处理
        
        订单流程：
        1. 将PlaceOrderRequest转换为StrategyOrder并缓存
        2. 按20个订单为一批进行批量下单（OKX API限制）
        3. 记录下单日志，便于后续审计和问题排查
        
        :param order_request_list: 下单请求对象列表
        :see: https://www.okx.com/docs-v5/zh/#rest-api-%E4%BA%A4%E6%98%93-%E5%A4%9A%E9%A1%B9%E4%B8%8B%E5%8D%95
        """
        order_data_list = []
        for order_request in order_request_list:
            # 创建策略订单对象，初始状态为已发送(SENT)
            strategy_order = StrategyOrder(
                inst_id=order_request.inst_id, ord_type=order_request.ord_type, side=order_request.side,
                size=order_request.size,
                price=order_request.price,
                client_order_id=order_request.client_order_id,
                strategy_order_status=StrategyOrderStatus.SENT, tgt_ccy=order_request.tgt_ccy
            )
            # 将策略订单存入缓存字典
            self._strategy_order_dict[order_request.client_order_id] = strategy_order
            # 将请求转换为API所需的字典格式
            order_data_list.append(order_request.to_dict())
            # 打印下单日志，包含关键订单信息
            print(f"PLACE ORDER {order_request.ord_type.value} {order_request.side.value} {order_request.inst_id} "
                  f"{order_request.size} @ {order_request.price}")
            # 达到20个订单时立即发送（OKX API批量下单上限）
            if len(order_data_list) >= 20:
                self._place_orders(order_data_list)
                order_data_list = []
        # 发送剩余不足20个的订单
        if order_data_list:
            self._place_orders(order_data_list)

    def _place_orders(self, order_data_list: List[Dict]):
        """
        内部使用的批量下单实现，处理API响应并更新订单状态
        
        此方法负责与OKX API直接交互，并处理下单结果：
        1. 成功下单的订单状态更新为已确认(ACK)
        2. 下单失败的订单从缓存中移除
        3. 处理API响应中的错误信息
        
        在加密货币交易中，订单确认状态跟踪至关重要，直接影响后续的订单管理决策
        
        :param order_data_list: API要求格式的订单数据列表
        :return: None
        """
        result = self.trade_api.place_multiple_orders(order_data_list)
        print(result)
        time.sleep(2)  # 短暂延迟，避免API请求频率超限
        if result["code"] == '1':
            # 整体请求失败，从缓存中移除所有相关订单
            for order_data in order_data_list:
                client_order_id = order_data['clOrdId']
                if client_order_id in self._strategy_order_dict:
                    del self._strategy_order_dict[client_order_id]
        else:
            # 处理单个订单的响应状态
            data = result['data']
            for single_order_data in data:
                client_order_id = single_order_data["clOrdId"]
                if client_order_id not in self._strategy_order_dict:
                    continue
                # 单个订单失败，从缓存中移除
                if single_order_data['sCode'] != '0':
                    del self._strategy_order_dict[client_order_id]
                    continue
                # 单个订单成功，更新订单ID和状态
                strategy_order: StrategyOrder = self._strategy_order_dict[client_order_id]
                strategy_order.order_id = single_order_data["ordId"]
                strategy_order.strategy_order_status = StrategyOrderStatus.ACK

    def amend_orders(self, order_request_list: List[AmendOrderRequest]):
        """
        批量修改订单，遵循OKX API限制（每次最多20个订单）
        
        在加密货币做市中，订单修改是动态调整策略的重要手段：
        1. 当市场价格变化时，调整挂单价格以保持竞争力
        2. 根据仓位变化调整订单数量，控制风险敞口
        3. 响应市场波动率变化，调整报价深度
        
        修改流程与下单类似，先更新本地缓存状态，再批量发送修改请求
        
        :param order_request_list: 修改订单请求对象列表
        :see: https://www.okx.com/docs-v5/zh/#rest-api-%E4%BA%A4%E6%98%93-%E5%A4%9A%E9%A1%B9%E4%BF%E6%94%B9%E5%AE%9A%E5%8D%95
        """
        order_data_list = []
        for order_request in order_request_list:
            client_order_id = order_request.client_order_id
            # 只处理缓存中存在的订单
            if client_order_id not in self._strategy_order_dict:
                continue
            strategy_order = self._strategy_order_dict[client_order_id]
            # 更新缓存中的订单信息
            if order_request.new_size:
                strategy_order.size = order_request.new_size
            if order_request.new_price:
                strategy_order.price = order_request.new_price
            # 设置修改请求ID和状态
            strategy_order.amend_req_id = order_request.req_id
            strategy_order.strategy_order_status = StrategyOrderStatus.AMD_SENT
            # 打印修改日志
            print(f"AMEND ORDER {order_request.client_order_id} with new size {order_request.new_size} or new price "
                  f"{order_request.new_price}, req_id is {order_request.req_id}")
            order_data_list.append(order_request.to_dict())
            # 达到20个订单时立即发送修改请求
            if len(order_data_list) >= 20:
                self._amend_orders(order_data_list)
                order_data_list = []
        # 发送剩余不足20个的修改请求
        if order_data_list:
            self._amend_orders(order_data_list)

    def _amend_orders(self, order_data_list: List[Dict]):
        """
        内部使用的批量修改订单实现，处理API响应并更新订单状态
        
        修改订单的状态更新逻辑与下单类似，但需要注意：
        1. 修改请求成功仅表示交易所已接收请求(AMD_ACK)
        2. 实际修改结果需通过订单状态更新事件确认
        3. 修改失败时订单仍保持原状态，无需从缓存中移除
        
        :param order_data_list: API要求格式的修改订单数据列表
        :return: None
        """
        result = self.trade_api.amend_multiple_orders(order_data_list)
        data = result['data']
        for single_order_data in data:
            client_order_id = single_order_data["clOrdId"]
            if client_order_id not in self._strategy_order_dict:
                continue
            # 仅当修改请求成功时更新状态
            if single_order_data['sCode'] != '0':
                continue
            strategy_order: StrategyOrder = self._strategy_order_dict[client_order_id]
            strategy_order.strategy_order_status = StrategyOrderStatus.AMD_ACK

    def cancel_orders(self, order_request_list: List[CancelOrderRequest]):
        """
        批量撤销订单，遵循OKX API限制（每次最多20个订单）
        
        在加密货币做市中，订单撤销通常基于以下原因：
        1. 市场价格快速波动，原挂单价格已不再合理
        2. 风险指标触发（如持仓超限、波动率突增）
        3. 策略周期结束或重新初始化
        4. 订单长时间未成交，需要更新报价
        
        :param order_request_list: 撤销订单请求对象列表
        :see: https://www.okx.com/docs-v5/zh/#rest-api-%E4%BA%A4%E6%98%93-%E5%A4%9A%E9%A1%B9%E5%8F%96%E6%B6%88%E5%AE%9A%E5%8D%95
        """
        order_data_list = []
        for order_request in order_request_list:
            client_order_id = order_request.client_order_id
            # 只处理缓存中存在的订单
            if client_order_id not in self._strategy_order_dict:
                continue
            strategy_order = self._strategy_order_dict[client_order_id]
            # 更新订单状态为撤销已发送
            strategy_order.strategy_order_status = StrategyOrderStatus.CXL_SENT
            # 打印撤销日志
            print(f"CANCELING ORDER {order_request.client_order_id}")
            order_data_list.append(order_request.to_dict())
            # 达到20个订单时立即发送撤销请求
            if len(order_data_list) >= 20:
                self._cancel_orders(order_data_list)
                order_data_list = []
        # 发送剩余不足20个的撤销请求
        if order_data_list:
            self._cancel_orders(order_data_list)

    def _cancel_orders(self, order_data_list: List[Dict]):
        """
        内部使用的批量撤销订单实现，处理API响应并更新订单状态
        
        撤销订单的状态更新逻辑与下单类似，但需要注意：
        1. 撤销成功后订单会从交易所订单簿中移除
        2. 部分交易所可能返回撤销请求已接收但实际仍在处理中
        3. 最终状态需通过订单更新事件确认
        
        :param order_data_list: API要求格式的撤销订单数据列表
        :return: None
        """
        result = self.trade_api.cancel_multiple_orders(order_data_list)
        data = result['data']
        for single_order_data in data:
            client_order_id = single_order_data["clOrdId"]
            if client_order_id not in self._strategy_order_dict:
                continue
            # 仅当撤销请求成功时更新状态
            if single_order_data['sCode'] != '0':
                continue
            strategy_order: StrategyOrder = self._strategy_order_dict[client_order_id]
            strategy_order.strategy_order_status = StrategyOrderStatus.CXL_ACK

    def cancel_all(self):
        """
        撤销所有现有策略订单，用于紧急风险控制或策略重置
        
        在加密货币做市中，此方法通常在以下场景使用：
        1. 市场出现异常波动，需要快速退出所有仓位
        2. 策略参数需要重大调整，先清除现有订单
        3. 检测到API连接异常或数据不同步
        4. 每日策略结算或定期重启
        
        实现逻辑：
        - 遍历所有策略订单缓存
        - 为每个订单创建撤销请求
        - 批量发送撤销请求
        
        注意：此方法仅撤销由当前策略管理的订单，不会影响手动下单或其他策略的订单
        """
        to_cancel = []
        for cid, strategy_order in self._strategy_order_dict.items():
            inst_id = strategy_order.inst_id
            cancel_req = CancelOrderRequest(inst_id=inst_id, client_order_id=cid)
            to_cancel.append(cancel_req)
        self.cancel_orders(to_cancel)

    def decide_td_mode(self, instrument: Instrument) -> TdMode:
        """
        根据账户模式和交易标的类型决定交易模式（保证金模式）
        
        在加密货币交易中，交易模式直接影响风险控制和资金利用率：
        - 非保证金模式（现货）：只能用已有的资金进行交易，风险较低
        - 逐仓保证金：每个交易对独立计算保证金，风险隔离
        - 全仓保证金：所有交易对共享保证金，风险和收益放大
        
        决策逻辑：
        1. 对于现货交易对，可选择非保证金或保证金模式
        2. 对于衍生品（SWAP/FUTURES/OPTION），必须使用保证金模式
        3. 具体模式由账户配置和策略参数共同决定
        
        :param instrument: 交易标的工具信息对象
        :return: 交易模式枚举值（TdMode）
        """
        return TdModeUtil.decide_trading_mode(self._account_mode, instrument.inst_type, TRADING_MODE)

    @staticmethod
    def get_order_book() -> OrderBook:
        """
        获取当前交易标的的订单簿数据，包含买卖盘口信息
        
        订单簿是做市商的核心数据来源，包含以下关键信息：
        - 买单（Bid）：市场上未成交的买入订单，按价格降序排列
        - 卖单（Ask）：市场上未成交的卖出订单，按价格升序排列
        - 深度：不同价格档位的订单数量，反映市场流动性
        
        在做市策略中，订单簿用于：
        1. 确定合理的报价价格（通常基于最佳买卖价）
        2. 计算市场深度，避免在流动性不足的价位挂单
        3. 检测大额订单（冰山订单）和市场冲击
        
        :return: 订单簿对象，包含买卖盘数据和更新时间戳
        :raises ValueError: 如果订单簿缓存未准备就绪
        """
        if TRADING_INSTRUMENT_ID not in order_books:
            raise ValueError(f"{TRADING_INSTRUMENT_ID} not ready in order books cache!")
        order_book: OrderBook = order_books[TRADING_INSTRUMENT_ID]
        return order_book

    @staticmethod
    def get_account() -> Account:
        """
        获取账户信息，包括余额、可用资金和账户状态
        
        在加密货币做市中，实时掌握账户状态至关重要：
        1. 监控可用资金，避免超额下单
        2. 跟踪资金变动，检测异常交易
        3. 计算风险指标，如资金使用率
        
        :return: 账户对象，包含总资产、可用资金、冻结资金等信息
        :raises ValueError: 如果账户缓存未准备就绪
        """
        if not account_container:
            raise ValueError(f"account information not ready in accounts cache!")
        account: Account = account_container[0]
        return account

    @staticmethod
    def get_positions() -> Positions:
        """
        获取当前持仓信息，包括各种交易标的的持仓数量和盈亏状态
        
        持仓管理是做市风险控制的核心：
        1. 监控持仓方向和数量，避免单向风险过大
        2. 计算持仓盈亏，评估策略表现
        3. 根据持仓情况调整报价策略（如持仓过多时倾向于平仓）
        
        :return: 头寸对象，包含所有交易标的的持仓信息
        :raises ValueError: 如果头寸缓存未准备就绪
        """
        if not positions_container:
            raise ValueError(f"positions information not ready in accounts cache!")
        positions: Positions = positions_container[0]
        return positions

    @staticmethod
    def get_tickers() -> Tickers:
        """
        获取市场行情信息，包括最新成交价、成交量和价格波动
        
        Tickers数据提供了市场的实时快照，用于：
        1. 确定做市基准价格
        2. 计算市场波动率，调整报价价差
        3. 检测价格趋势，避免逆势做单
        
        :return: 行情对象，包含最新价、最高价、最低价、成交量等信息
        :raises ValueError: 如果行情缓存未准备就绪
        """

    @staticmethod
    def get_orders() -> Orders:
        """
        获取当前所有交易所订单的快照，用于订单状态同步和策略决策
        
        在加密货币做市中，订单状态同步是确保策略正确性的关键：
        1. 验证策略订单是否成功提交到交易所
        2. 跟踪订单成交情况（部分成交/完全成交）
        3. 检测异常订单状态（如被拒绝、过期等）
        
        实现细节：
        - 返回订单容器的深拷贝，防止外部修改影响内部状态
        - 包含所有类型的订单，不仅限于当前策略创建的订单
        
        :return: 包含所有订单信息的Orders对象
        :raises ValueError: 如果订单缓存未准备就绪
        """
        if not orders_container:
            raise ValueError(f"order information not ready in orders cache!")
        orders: Orders = orders_container[0]
        return deepcopy(orders)

    def _health_check(self) -> bool:
        """
        策略健康检查，确保市场数据和账户信息正常，是做市风险控制的第一道防线
        
        健康检查在加密货币做市中至关重要，因为实时市场数据和账户状态的准确性直接影响：
        1. 订单定价合理性
        2. 风险敞口控制
        3. 策略决策有效性
        
        检查项包括：
        1. 订单簿数据新鲜度（延迟不超过设定阈值）
        2. 订单簿校验和（确保数据完整性，防止传输错误）
        3. 账户信息时效性
        
        :return: True表示健康状态良好，False表示存在异常需要处理
        """
        try:
            order_book: OrderBook = self.get_order_book()
        except ValueError:
            return False
        # 检查订单簿延迟（毫秒转秒）
        order_book_delay = time.time() - order_book.timestamp / 1000
        if order_book.timestamp and order_book_delay > ORDER_BOOK_DELAYED_SEC:
            logging.warning(f"{TRADING_INSTRUMENT_ID} delayed in order books cache for {order_book_delay:.2f} seconds!")
            return False
        # 验证订单簿数据完整性
        check_sum_result: bool = order_book.do_check_sum()
        if not check_sum_result:
            logging.warning(f"{TRADING_INSTRUMENT_ID} orderbook checksum failed, re-subscribe MDS!")
            self.mds.stop_service()
            self.mds.run_service()
            return False
        try:
            account = self.get_account()
        except ValueError:
            return False
        # 检查账户数据延迟
        account_delay = time.time() - account.u_time / 1000
        if account_delay > ACCOUNT_DELAYED_SEC:
            logging.warning(f"Account info delayed in accounts cache for {account_delay:.2f} seconds!")
            return False
        return True

    def _update_strategy_order_status(self):
        """
        更新策略订单状态，同步交易所订单状态到本地缓存
        
        在加密货币做市中，订单状态同步是确保策略正确运行的核心机制：
        1. 跟踪订单从提交到成交/撤销的全生命周期
        2. 计算实际成交数量和均价，用于盈亏分析
        3. 更新交易统计指标（成交量、买卖方向等）
        4. 清理已完成（成交/撤销）的订单，释放资源
        
        实现逻辑：
        - 对比本地缓存订单与交易所实际订单状态
        - 处理部分成交订单的累计成交量
        - 更新策略绩效指标（净持仓、交易量等）
        - 移除已终止状态的订单
        """
        orders_cache: Orders = self.get_orders()
        order_not_found_in_cache = {}  # 未在交易所找到的策略订单
        order_to_remove_from_cache = []  # 需要从缓存中移除的订单
        
        # 遍历所有策略订单，与交易所订单状态同步
        for client_order_id in self._strategy_order_dict.copy():
            # 从交易所订单缓存中查找对应订单
            exchange_order: Order = orders_cache.get_order_by_client_order_id(client_order_id=client_order_id)
            strategy_order = self._strategy_order_dict[client_order_id]
            
            # 记录未在交易所找到的订单（可能已过期或被拒绝）
            if not exchange_order:
                order_not_found_in_cache[client_order_id] = strategy_order
                continue
            
            # 计算本次更新的成交数量
            filled_size_from_update = Decimal(exchange_order.acc_fill_sz) - Decimal(strategy_order.filled_size)
            # 买入为正，卖出为负
            side_flag = 1 if exchange_order.side == OrderSide.BUY else -1
            
            # 更新策略绩效指标
            self._strategy_measurement.net_filled_qty += filled_size_from_update * side_flag
            self._strategy_measurement.trading_volume += filled_size_from_update
            if side_flag == 1:
                self._strategy_measurement.buy_filled_qty += filled_size_from_update
            else:
                self._strategy_measurement.sell_filled_qty += filled_size_from_update
            
            # 更新订单状态
            if exchange_order.state == OrderState.LIVE:
                strategy_order.strategy_order_status = StrategyOrderStatus.LIVE
            elif exchange_order.state == OrderState.PARTIALLY_FILLED:
                strategy_order.strategy_order_status = StrategyOrderStatus.PARTIALLY_FILLED
                strategy_order.filled_size = exchange_order.acc_fill_sz
                strategy_order.avg_fill_price = exchange_order.fill_px
            # 处理已完成订单（成交或撤销）
            elif exchange_order.state in [OrderState.CANCELED, OrderState.FILLED, OrderState.REJECTED]:
                del self._strategy_order_dict[client_order_id]
                order_to_remove_from_cache.append(exchange_order)
        
        # 清理已完成订单
        orders_cache.remove_orders(order_to_remove_from_cache)
        # 记录未找到的订单（可能需要人工干预）
        if order_not_found_in_cache:
            logging.warning(f"Strategy Orders not found in order cache: {order_not_found_in_cache}")

    def get_params(self):
        """
        加载并更新策略参数配置，支持运行时动态调整
        
        在加密货币做市中，参数动态调整是适应市场变化的关键：
        1. 网格间距、订单数量等核心做市参数
        2. 风险控制阈值（如最大持仓、最大单笔订单）
        3. 报价偏移和价差设置
        
        参数来源通常包括：
        - 配置文件（如params.yaml）
        - 环境变量
        - 远程配置服务（高级特性）
        
        调用此方法会重新加载参数，无需重启策略即可应用新配置
        """
        self.params_loader.load_params()

    def get_strategy_measurement(self):
        """
        获取策略绩效测量对象，包含做市关键指标
        
        做市商需要实时监控的核心指标包括：
        1. 净持仓量：反映市场方向风险敞口
        2. 总交易量：衡量做市活跃度和收益潜力
        3. 买卖方向分布：评估市场偏向
        4. 盈亏状况：衡量策略盈利能力
        
        :return: 包含绩效指标的StrategyMeasurement对象
        """
        return self._strategy_measurement

    def risk_summary(self):
        """
        生成风险摘要，评估当前市场风险和策略风险敞口
        
        在加密货币做市中，风险控制是生存的关键。此方法：
        1. 生成当前风险快照（账户、持仓、市场行情）
        2. 计算关键风险指标（如VAR、 Greeks等衍生品指标）
        3. 更新策略绩效测量
        
        风险快照包含：
        - 账户余额和可用资金
        - 各交易对持仓数量和方向
        - 标记价格和市场波动
        
        这些信息用于判断是否需要调整做市策略或进行风险对冲
        """
        account = self.get_account()
        positions = self.get_positions()
        tickers = tickers_container[0]
        mark_px_cache = mark_px_container[0]
        risk_snapshot = RiskCalculator.generate_risk_snapshot(account, positions, tickers, mark_px_cache)
        self._strategy_measurement.consume_risk_snapshot(risk_snapshot)

    def check_status(self):
        """
        检查OKX交易所系统状态，避免在维护期间进行交易
        
        加密货币交易所会定期进行系统维护，期间可能暂停交易或数据更新
        在此期间进行做市可能导致：
        - 订单无法成交
        - 市场数据延迟或不准确
        - API响应异常
        
        实现逻辑：
        - 查询交易所状态API
        - 检查是否有正在进行或即将进行的维护
        - 返回维护状态，决定是否继续做市
        
        :return: True表示交易所正常，False表示存在维护或异常
        """
        status_response = self.status_api.status("ongoing")
        if status_response.get("data"):
            print(status_response.get("data"))
            return False
        return True

    def _set_account_config(self):
        """
        获取并设置账户配置模式（现金/单币种保证金/多币种保证金/组合保证金）
        
        账户模式决定了：
        1. 可用的交易类型（现货/保证金/衍生品）
        2. 保证金计算方式
        3. 风险控制规则
        4. 资金利用率
        
        实现逻辑：通过账户API获取账户等级，映射为对应的账户配置模式枚举值
        
        异常处理：
        - 捕获httpx.ConnectError连接错误并重试最多3次
        - 其他异常将被重新抛出
        
        :raises httpx.ConnectError: 当网络连接失败且重试超过限制时
        :raises Exception: 当API返回错误码时
        """
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                account_config = self.account_api.get_account_config()
                
                if account_config.get("code") == '0':
                    self._account_mode = AccountConfigMode(int(account_config.get("data")[0]['acctLv']))
                    return  # 成功获取配置后直接返回
                else:
                    raise Exception(f"Account API returned error code: {account_config.get('code')}")
            except httpx.ConnectError as e:
                retry_count += 1
                print(f"连接错误 (尝试 {retry_count}/{max_retries}): {e}")
                if retry_count >= max_retries:
                    raise  # 重试次数用尽后重新抛出异常
                time.sleep(1)  # 等待1秒后重试
            except Exception as e:
                # 对于非连接错误，直接抛出
                raise

    async def _run_exchange_connection(self):
        """
        异步启动并运行所有交易所连接服务（市场数据、订单、仓位）
        
        参数：
            无
        返回值：
            无
        异常：
            如果任何服务启动失败，将抛出相应的异常
        
        做市策略依赖多个实时数据流：
        1. 市场数据服务（MDS）：提供订单簿和成交数据
        2. 订单管理服务（OMS）：处理订单提交和状态更新
        3. 仓位管理服务（PMS）：跟踪账户余额和持仓变化
        
        实现流程：
        - 启动WebSocket连接
        - 订阅相关频道
        - 开始数据接收和处理循环
        
        注意：此方法会阻塞当前线程，通常在单独线程中运行
        """
        # 异步启动各服务并等待完成
        await self.mds.start()
        await self.oms.start()
        await self.pms.start()
        self.rest_mds.start()
        # 异步运行各服务
        await self.mds.run_service()
        await self.oms.run_service()
        await self.pms.run_service()

    def trading_instrument_type(self) -> InstType:
        """
        根据交易标的ID和账户模式确定实际交易类型
        
        在OKX交易所中，相同的交易对ID可能对应不同的交易类型：
        - BTC-USDT在现金账户是现货
        - BTC-USDT在保证金账户可以是现货或保证金交易
        
        决策逻辑：
        1. 从交易对ID猜测基本类型（现货/永续/期货等）
        2. 根据账户模式和交易模式调整实际类型
        3. 现货在保证金账户可转为保证金交易
        
        :return: 实际交易类型枚举值
        """
        guessed_inst_type = InstrumentUtil.get_inst_type_from_inst_id(TRADING_INSTRUMENT_ID)
        if guessed_inst_type == InstType.SPOT:
            if self._account_mode == AccountConfigMode.CASH:
                return InstType.SPOT
            if self._account_mode == AccountConfigMode.SINGLE_CCY_MARGIN:
                if TRADING_MODE == TdMode.CASH.value:
                    return InstType.SPOT
                return InstType.MARGIN
            if self._account_mode in [AccountConfigMode.MULTI_CCY_MARGIN, AccountConfigMode.PORTFOLIO_MARGIN]:
                if TRADING_MODE == TdMode.ISOLATED.value:
                    return InstType.MARGIN
                return InstType.SPOT
        return guessed_inst_type

    def set_strategy_measurement(self, trading_instrument, trading_instrument_type: InstType):
        """
        初始化策略绩效测量对象，设置交易标的和类型
        
        绩效测量是做市策略优化的基础，需要明确：
        - 交易标的（如BTC-USDT）
        - 交易类型（现货/永续/期货）
        
        这些信息用于：
        1. 计算正确的盈亏
        2. 适配不同交易类型的规则
        3. 生成针对性的绩效报告
        
        :param trading_instrument: 交易标的ID
        :param trading_instrument_type: 交易类型
        """
        self._strategy_measurement = StrategyMeasurement(trading_instrument=trading_instrument,
                                                         trading_instrument_type=trading_instrument_type)

    async def run(self):
        """
        异步做市策略主运行循环，协调所有组件执行做市流程
        
        参数：
            无
        返回值：
            无
        异常：
            如果运行过程中出现异常，将被捕获并处理
        
        这是策略的核心入口点，实现了完整的做市生命周期：
        1. 初始化阶段：账户配置、服务连接、参数加载
        2. 运行阶段：健康检查、风险评估、订单决策、订单管理
        3. 异常处理：错误恢复、紧急撤单、状态重置
        
        主循环流程详解：
        - 检查交易所状态，确保系统正常
        - 加载最新策略参数
        - 执行健康检查（数据新鲜度、完整性）
        - 生成风险摘要，评估当前市场风险
        - 同步订单状态，清理已完成订单
        - 调用order_operation_decision生成订单决策
        - 执行订单操作（下单、改单、撤单）
        - 短暂休眠后重复循环
        
        异常处理机制：
        - 捕获并记录所有异常
        - 发生异常时尝试撤销所有订单
        - 延迟后重试，避免频繁失败
        """
        self._set_account_config()
        self.trading_instrument_type = self.trading_instrument_type()
        InstrumentUtil.get_instrument(TRADING_INSTRUMENT_ID, self.trading_instrument_type)
        self.set_strategy_measurement(trading_instrument=TRADING_INSTRUMENT_ID,
                                      trading_instrument_type=self.trading_instrument_type)
        await self._run_exchange_connection()
        while 1:
            try:
                # 检查交易所状态，避免在维护期间交易
                exchange_normal = self.check_status()
                if not exchange_normal:
                    raise ValueError("There is a ongoing maintenance in OKX.")
                
                # 加载最新策略参数
                self.get_params()
                
                # 执行健康检查，确保数据正常
                result = self._health_check()
                
                # 生成风险摘要
                self.risk_summary()
                
                # 健康检查失败时延迟重试
                if not result:
                    print(f"Health Check result is {result}")
                    time.sleep(5)
                    continue
                
                # 同步订单状态
                self._update_strategy_order_status()
                
                # 核心订单决策逻辑（由子类实现）
                place_order_list, amend_order_list, cancel_order_list = self.order_operation_decision()
                # print(place_order_list)
                # print(amend_order_list)
                # print(cancel_order_list)
                # 执行订单操作
                self.place_orders(place_order_list)
                self.amend_orders(amend_order_list)
                self.cancel_orders(cancel_order_list)
                
                # 控制循环频率，避免API请求过于频繁
                time.sleep(1)
            except:
                # 捕获所有异常，打印堆栈信息便于调试
                print(traceback.format_exc())
                try:
                    # 发生异常时尝试撤销所有订单，控制风险
                    self.cancel_all()
                except:
                    print(f"Failed to cancel orders: {traceback.format_exc()}")
                # 异常后延迟更长时间再重试
                time.sleep(20)
