from fastapi import APIRouter
from plugins.plugin_base import PluginBase

class ExamplePlugin(PluginBase):
    """示例插件，演示插件系统的基本功能"""
    
    def __init__(self):
        """初始化示例插件"""
        super().__init__("example_plugin", "1.0.0")
        # 创建API路由
        self.router = APIRouter(prefix="/api/plugins/example")
        self._setup_routes()
    
    def _setup_routes(self):
        """设置API路由"""
        @self.router.get("/")
        def example_root():
            """示例根路由"""
            return {
                "message": "Hello from example plugin!",
                "plugin_name": self.name,
                "version": self.version
            }
        
        @self.router.get("/test")
        def example_test():
            """示例测试路由"""
            return {
                "test": "success",
                "data": {
                    "key1": "value1",
                    "key2": "value2"
                }
            }
    
    def register(self, plugin_manager):
        """注册插件"""
        super().register(plugin_manager)
        self.logger.info(f"{self.name} 插件注册成功，版本: {self.version}")
    
    def start(self):
        """启动插件"""
        super().start()
        self.logger.info(f"{self.name} 插件启动成功")
    
    def stop(self):
        """停止插件"""
        super().stop()
        self.logger.info(f"{self.name} 插件停止成功")

def register_plugin():
    """注册插件的入口函数"""
    return ExamplePlugin()
