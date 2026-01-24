import importlib
from .__init__ import Exchange

class ExchangeFactory:
    @staticmethod
    def create_exchange(exchange_name, config: dict = None) -> Exchange:
        """
        创建交易所实例
        
        Args:
            exchange_name: 交易所名称
            config: 交易所配置，默认从配置文件读取
            
        Returns:
            Exchange: 交易所实例
            
        Raises:
            ValueError: 当交易所不支持或类未找到时
        """
        # 尝试从配置文件读取配置
        if config is None:
            try:
                from backend.config_manager import load_system_configs
                configs = load_system_configs()
                config = configs.get('exchange', {}).get(exchange_name, {})
            except ImportError:
                config = {}
        
        # 构建模块名和类名
        module_name = f"exchange.{exchange_name.lower()}"
        class_name = f"{exchange_name.capitalize()}Exchange"
        
        try:
            # 导入模块
            module = importlib.import_module(module_name)
            
            # 获取交易所类
            exchange_class = getattr(module, class_name)
            
            # 创建并返回交易所实例
            return exchange_class(
                exchange_name=exchange_name,
                api_key=config.get('api_key'),
                secret_key=config.get('secret_key'),
                trading_mode=config.get('trading_mode'),
                proxy_url=config.get('proxy_url'),
                testnet=config.get('testnet', False)
            )
        except ImportError as e:
            raise ValueError(f"Exchange {exchange_name} is not supported: {e}")
        except AttributeError as e:
            raise ValueError(f"Class {class_name} not found in {module_name}: {e}")
