from abc import ABC, abstractmethod
import pandas as pd

class Exchange(ABC):
    def __init__(self, exchange_name, api_key, secret_key, trading_mode, proxy_url, testnet=False, api_passphrase=None):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.secret_key = secret_key
        self.proxy_url = proxy_url
        self.trading_mode = trading_mode
        self.testnet = testnet
    
    @abstractmethod
    def download_data(self, *args, **kwargs):
        pass

    @abstractmethod
    def load_data(self, *args, **kwargs) -> pd.DataFrame:
        pass

    @abstractmethod
    def health_check(self) -> bool:
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
        pass

    @abstractmethod
    def set_account_config(self):
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
        pass
