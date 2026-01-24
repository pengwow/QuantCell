# 币安数据解析器
import json
from typing import Dict, Any, Optional
from loguru import logger


class BinanceDataParser:
    """币安WebSocket数据解析器，负责将原始消息解析为统一格式"""
    
    def __init__(self):
        """初始化币安数据解析器"""
        self.supported_data_types = {
            'kline',
            'depth',
            'aggTrade',
            'trade',
            'ticker',
            'miniTicker',
            'bookTicker'
        }
    
    def parse_message(self, raw_message: str) -> Optional[Dict[str, Any]]:
        """
        解析原始WebSocket消息
        
        Args:
            raw_message: 原始WebSocket消息字符串
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的消息，None表示解析失败
        """
        try:
            # 解析JSON格式
            message = json.loads(raw_message)
            
            # 处理不同类型的消息
            if 'stream' in message:
                # 处理订阅消息
                stream = message['stream']
                data = message['data']
                
                # 解析数据流名称
                stream_parts = stream.split('@')
                if len(stream_parts) < 2:
                    logger.warning(f"无效的数据流名称: {stream}")
                    return None
                
                symbol = stream_parts[0]
                data_type = stream_parts[1].split('_')[0]
                
                if data_type not in self.supported_data_types:
                    logger.warning(f"不支持的数据类型: {data_type}")
                    return None
                
                # 调用对应的解析方法
                parser_method = getattr(self, f"_parse_{data_type}", None)
                if parser_method:
                    parsed_data = parser_method(symbol, data)
                    if parsed_data:
                        parsed_data['exchange'] = 'binance'
                        parsed_data['data_type'] = data_type
                        return parsed_data
                else:
                    logger.warning(f"未实现的数据类型解析方法: {data_type}")
            elif 'result' in message:
                # 处理订阅确认消息
                logger.debug(f"订阅确认消息: {message}")
            elif 'e' in message:
                # 处理推送消息（不同格式）
                event_type = message['e']
                data_type = event_type.lower()
                
                if data_type not in self.supported_data_types:
                    logger.warning(f"不支持的事件类型: {event_type}")
                    return None
                
                # 调用对应的解析方法
                parser_method = getattr(self, f"_parse_{data_type}", None)
                if parser_method:
                    symbol = message.get('s', '')
                    parsed_data = parser_method(symbol, message)
                    if parsed_data:
                        parsed_data['exchange'] = 'binance'
                        parsed_data['data_type'] = data_type
                        return parsed_data
                else:
                    logger.warning(f"未实现的事件类型解析方法: {event_type}")
            else:
                logger.warning(f"未知的消息格式: {message}")
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}, 原始消息: {raw_message}")
        except Exception as e:
            logger.error(f"数据解析错误: {e}, 原始消息: {raw_message}")
        
        return None
    
    def _parse_kline(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析K线数据
        
        Args:
            symbol: 交易对
            data: K线数据
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的K线数据
        """
        try:
            # 处理不同格式的K线数据
            if isinstance(data, dict):
                # 格式1: 直接包含k字段
                kline_data = data.get('k', data)
            else:
                logger.warning(f"无效的K线数据格式: {data}")
                return None
            
            return {
                'symbol': symbol,
                'open_time': int(kline_data.get('t', 0)),
                'open': float(kline_data.get('o', 0)),
                'high': float(kline_data.get('h', 0)),
                'low': float(kline_data.get('l', 0)),
                'close': float(kline_data.get('c', 0)),
                'volume': float(kline_data.get('v', 0)),
                'close_time': int(kline_data.get('T', 0)),
                'quote_volume': float(kline_data.get('q', 0)),
                'trades': int(kline_data.get('n', 0)),
                'taker_buy_base_volume': float(kline_data.get('V', 0)),
                'taker_buy_quote_volume': float(kline_data.get('Q', 0)),
                'interval': kline_data.get('i', ''),
                'is_final': kline_data.get('x', False)
            }
        except Exception as e:
            logger.error(f"K线数据解析错误: {e}, 数据: {data}")
            return None
    
    def _parse_depth(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析深度数据
        
        Args:
            symbol: 交易对
            data: 深度数据
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的深度数据
        """
        try:
            return {
                'symbol': symbol,
                'last_update_id': int(data.get('lastUpdateId', 0)),
                'bids': [[float(price), float(quantity)] for price, quantity in data.get('bids', [])],
                'asks': [[float(price), float(quantity)] for price, quantity in data.get('asks', [])],
                'event_time': int(data.get('E', 0))
            }
        except Exception as e:
            logger.error(f"深度数据解析错误: {e}, 数据: {data}")
            return None
    
    def _parse_aggtrade(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析聚合交易数据
        
        Args:
            symbol: 交易对
            data: 聚合交易数据
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的聚合交易数据
        """
        try:
            return {
                'symbol': symbol,
                'agg_trade_id': int(data.get('a', 0)),
                'price': float(data.get('p', 0)),
                'quantity': float(data.get('q', 0)),
                'first_trade_id': int(data.get('f', 0)),
                'last_trade_id': int(data.get('l', 0)),
                'trade_time': int(data.get('T', 0)),
                'is_buyer_maker': data.get('m', False),
                'event_time': int(data.get('E', 0))
            }
        except Exception as e:
            logger.error(f"聚合交易数据解析错误: {e}, 数据: {data}")
            return None
    
    def _parse_trade(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析交易数据
        
        Args:
            symbol: 交易对
            data: 交易数据
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的交易数据
        """
        try:
            return {
                'symbol': symbol,
                'trade_id': int(data.get('t', 0)),
                'price': float(data.get('p', 0)),
                'quantity': float(data.get('q', 0)),
                'buyer_order_id': int(data.get('b', 0)),
                'seller_order_id': int(data.get('a', 0)),
                'trade_time': int(data.get('T', 0)),
                'is_buyer_maker': data.get('m', False),
                'event_time': int(data.get('E', 0))
            }
        except Exception as e:
            logger.error(f"交易数据解析错误: {e}, 数据: {data}")
            return None
    
    def _parse_ticker(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析完整行情数据
        
        Args:
            symbol: 交易对
            data: 完整行情数据
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的完整行情数据
        """
        try:
            return {
                'symbol': symbol,
                'event_time': int(data.get('E', 0)),
                'price_change': float(data.get('p', 0)),
                'price_change_percent': float(data.get('P', 0)),
                'weighted_avg_price': float(data.get('w', 0)),
                'prev_close_price': float(data.get('x', 0)),
                'last_price': float(data.get('c', 0)),
                'last_quantity': float(data.get('Q', 0)),
                'bid_price': float(data.get('b', 0)),
                'bid_quantity': float(data.get('B', 0)),
                'ask_price': float(data.get('a', 0)),
                'ask_quantity': float(data.get('A', 0)),
                'open_price': float(data.get('o', 0)),
                'high_price': float(data.get('h', 0)),
                'low_price': float(data.get('l', 0)),
                'volume': float(data.get('v', 0)),
                'quote_volume': float(data.get('q', 0)),
                'open_time': int(data.get('O', 0)),
                'close_time': int(data.get('C', 0)),
                'first_trade_id': int(data.get('F', 0)),
                'last_trade_id': int(data.get('L', 0)),
                'trade_count': int(data.get('n', 0))
            }
        except Exception as e:
            logger.error(f"完整行情数据解析错误: {e}, 数据: {data}")
            return None
    
    def _parse_miniticker(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析迷你行情数据
        
        Args:
            symbol: 交易对
            data: 迷你行情数据
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的迷你行情数据
        """
        try:
            return {
                'symbol': symbol,
                'event_time': int(data.get('E', 0)),
                'open_price': float(data.get('o', 0)),
                'high_price': float(data.get('h', 0)),
                'low_price': float(data.get('l', 0)),
                'close_price': float(data.get('c', 0)),
                'volume': float(data.get('v', 0)),
                'quote_volume': float(data.get('q', 0))
            }
        except Exception as e:
            logger.error(f"迷你行情数据解析错误: {e}, 数据: {data}")
            return None
    
    def _parse_bookticker(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析最优买卖盘数据
        
        Args:
            symbol: 交易对
            data: 最优买卖盘数据
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的最优买卖盘数据
        """
        try:
            return {
                'symbol': symbol,
                'bid_price': float(data.get('b', 0)),
                'bid_quantity': float(data.get('B', 0)),
                'ask_price': float(data.get('a', 0)),
                'ask_quantity': float(data.get('A', 0)),
                'event_time': int(data.get('T', 0)),
                'transaction_time': int(data.get('E', 0))
            }
        except Exception as e:
            logger.error(f"最优买卖盘数据解析错误: {e}, 数据: {data}")
            return None