import os
import sys
import json
import importlib.util
from typing import Dict, List, Any
from loguru import logger
from fastapi import FastAPI, APIRouter
from .plugin_base import PluginBase

class PluginManager:
    """插件管理器，负责扫描、加载、初始化和管理插件"""
    
    def __init__(self, plugin_dir: str = None):
        """初始化插件管理器
        
        Args:
            plugin_dir: 插件目录，默认为backend/plugins
        """
        self.plugin_dir = plugin_dir or os.path.join(os.path.dirname(__file__), "..", "plugins")
        self.plugins: Dict[str, PluginBase] = {}
        self.plugin_routes: Dict[str, APIRouter] = {}
        self.logger = logger.bind(component="plugin_manager")
    
    def scan_plugins(self) -> List[str]:
        """扫描插件目录，返回所有插件名称
        
        Returns:
            插件名称列表
        """
        plugin_names = []
        
        if not os.path.exists(self.plugin_dir):
            self.logger.warning(f"插件目录 {self.plugin_dir} 不存在")
            return plugin_names
        
        for item in os.listdir(self.plugin_dir):
            item_path = os.path.join(self.plugin_dir, item)
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "manifest.json")):
                plugin_names.append(item)
        
        self.logger.info(f"发现 {len(plugin_names)} 个插件: {plugin_names}")
        return plugin_names
    
    def load_plugin(self, plugin_name: str) -> bool:
        """加载指定插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            加载成功返回True，否则返回False
        """
        try:
            plugin_path = os.path.join(self.plugin_dir, plugin_name)
            manifest_path = os.path.join(plugin_path, "manifest.json")
            
            # 读取插件清单
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            # 动态导入插件模块
            main_module = manifest.get("main", "plugin.py")
            plugin_module_path = os.path.join(plugin_path, main_module)
            
            # 将插件目录添加到sys.path
            if plugin_path not in sys.path:
                sys.path.insert(0, plugin_path)
            
            # 导入插件模块
            spec = importlib.util.spec_from_file_location(f"plugins.{plugin_name}.plugin", plugin_module_path)
            if spec and spec.loader:
                plugin_module = importlib.util.module_from_spec(spec)
                sys.modules[f"plugins.{plugin_name}.plugin"] = plugin_module
                spec.loader.exec_module(plugin_module)
                
                # 获取注册插件的函数
                if hasattr(plugin_module, "register_plugin"):
                    plugin = plugin_module.register_plugin()
                    if isinstance(plugin, PluginBase):
                        # 注册插件
                        plugin.register(self)
                        self.plugins[plugin_name] = plugin
                        
                        # 加载插件路由
                        if hasattr(plugin, "router") and isinstance(plugin.router, APIRouter):
                            self.plugin_routes[plugin_name] = plugin.router
                        
                        # 启动插件
                        plugin.start()
                        
                        self.logger.info(f"插件 {plugin_name} 加载成功")
                        return True
                    else:
                        self.logger.error(f"插件 {plugin_name} 不是 PluginBase 的实例")
                else:
                    self.logger.error(f"插件 {plugin_name} 没有 register_plugin 函数")
            
        except Exception as e:
            self.logger.error(f"加载插件 {plugin_name} 失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        return False
    
    def load_all_plugins(self) -> List[str]:
        """加载所有插件
        
        Returns:
            成功加载的插件名称列表
        """
        plugin_names = self.scan_plugins()
        loaded_plugins = []
        
        for plugin_name in plugin_names:
            if self.load_plugin(plugin_name):
                loaded_plugins.append(plugin_name)
        
        self.logger.info(f"成功加载 {len(loaded_plugins)} 个插件")
        return loaded_plugins
    
    def register_plugins(self, app: FastAPI) -> None:
        """将所有插件路由注册到FastAPI应用
        
        Args:
            app: FastAPI应用实例
        """
        for plugin_name, router in self.plugin_routes.items():
            app.include_router(router, tags=[f"plugin-{plugin_name}"])
            self.logger.info(f"插件 {plugin_name} 路由注册成功")
    
    def get_plugin(self, plugin_name: str) -> PluginBase or None:
        """获取指定插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            插件实例，不存在返回None
        """
        return self.plugins.get(plugin_name)
    
    def get_all_plugins(self) -> Dict[str, PluginBase]:
        """获取所有插件
        
        Returns:
            插件字典
        """
        return self.plugins
    
    def stop_all_plugins(self) -> None:
        """停止所有插件"""
        for plugin_name, plugin in self.plugins.items():
            try:
                plugin.stop()
                self.logger.info(f"插件 {plugin_name} 停止成功")
            except Exception as e:
                self.logger.error(f"停止插件 {plugin_name} 失败: {e}")
