#!/usr/bin/env python3
"""
配置文件管理模块

用于处理config.toml配置文件的读写操作，与系统配置表兼容
支持配置的导入导出、TOML与JSON格式转换
使用tomli和tomli-w库进行TOML读写
"""

import sys
import json
import tomli
import tomli_w
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from collector.db.database import SessionLocal, init_database_config
from collector.db.models import SystemConfig
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class ConfigManager:
    """配置文件管理器
    
    用于处理config.toml配置文件的读写操作
    支持与系统配置表的数据结构兼容
    提供TOML与JSON格式转换功能
    """
    
    def __init__(self, config_path: str = ""):
        """初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认使用backend/config.toml
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            # 默认配置文件路径
            current_dir = Path(__file__).parent.parent
            self.config_path = current_dir / "config.toml"
        
        logger.info(f"配置文件路径: {self.config_path}")
    
    def read_config(self) -> Dict[str, Any]:
        """读取配置文件
        
        Returns:
            Dict[str, Any]: 配置数据
        """
        try:
            if not self.config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}")
                return {}
            
            with open(self.config_path, 'rb') as f:
                config_data = tomli.load(f)
            
            logger.info(f"成功读取配置文件: {self.config_path}")
            return config_data
        except Exception as e:
            logger.error(f"读取配置文件失败: {str(e)}")
            return {}
    
    def write_config(self, config_data: Dict[str, Any]) -> bool:
        """写入配置文件
        
        Args:
            config_data: 配置数据
            
        Returns:
            bool: 写入成功返回True，失败返回False
        """
        try:
            # 确保配置文件目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'wb') as f:
                tomli_w.dump(config_data, f)
            
            logger.info(f"成功写入配置文件: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"写入配置文件失败: {str(e)}")
            return False
    
    def save_config_items(self, config_items: List[Dict[str, Any]]) -> bool:
        """保存配置项到配置文件
        
        Args:
            config_items: 配置项列表，每个配置项包含key, value, description, name等字段
            
        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            # 读取现有配置
            existing_config = self.read_config()
            
            # 按name分组配置项
            config_groups = {}
            for item in config_items:
                name = item.get('name', 'system')
                if name not in config_groups:
                    config_groups[name] = {}
                
                # 处理value类型
                value = item.get('value')
                # 直接使用原始值，不进行类型转换
                config_groups[name][item['key']] = value
            
            # 将分组后的配置写入配置文件
            for group_name, group_config in config_groups.items():
                existing_config[group_name] = group_config
            
            # 写入配置文件
            return self.write_config(existing_config)
        except Exception as e:
            logger.error(f"保存配置项失败: {str(e)}")
            return False
    
    def get_config_by_group(self, group_name: str) -> Dict[str, Any]:
        """获取指定分组的配置
        
        Args:
            group_name: 分组名称
            
        Returns:
            Dict[str, Any]: 分组配置
        """
        config_data = self.read_config()
        return config_data.get(group_name, {})
    
    def get_config_item(self, group_name: str, key: str, default: Any = None) -> Any:
        """获取指定分组的指定配置项
        
        Args:
            group_name: 分组名称
            key: 配置键名
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        config_data = self.read_config()
        group_config = config_data.get(group_name, {})
        return group_config.get(key, default)
    
    def update_config_item(self, group_name: str, key: str, value: Any) -> bool:
        """更新指定分组的指定配置项
        
        Args:
            group_name: 分组名称
            key: 配置键名
            value: 配置值
            
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            # 读取现有配置
            existing_config = self.read_config()
            
            # 确保分组存在
            if group_name not in existing_config:
                existing_config[group_name] = {}
            
            # 直接使用原始值，不进行类型转换
            existing_config[group_name][key] = value
            
            # 写入配置文件
            return self.write_config(existing_config)
        except Exception as e:
            logger.error(f"更新配置项失败: {str(e)}")
            return False
    
    # ==================== 配置导入导出功能（原config_io.py）====================
    
    @staticmethod
    def export_to_toml(output_path: Optional[str] = None, include_sensitive: bool = False, use_hierarchy: bool = True) -> str:
        """将系统配置导出为TOML文件

        Args:
            output_path: 输出文件路径，默认为项目根目录下的 config.toml
            include_sensitive: 是否包含敏感配置（密码等）
            use_hierarchy: 是否使用层级结构导出（基于key中的点号）

        Returns:
            str: 导出的文件路径
        """
        init_database_config()
        db: Session = SessionLocal()

        try:
            if use_hierarchy:
                # 使用层级结构导出
                export_data = ConfigManager._export_hierarchical(db, include_sensitive)
            else:
                # 使用扁平化导出（兼容旧方式）
                export_data = ConfigManager._export_flat(db, include_sensitive)

            # 添加导出元数据
            export_data["_meta"] = {
                "export_time": datetime.now().isoformat(),
                "version": "1.1",
                "total_configs": db.query(SystemConfig).count(),
                "include_sensitive": include_sensitive,
                "hierarchical": use_hierarchy
            }

            # 确定输出路径
            if output_path is None:
                output_file_path: Path = project_root / "config.toml"
            else:
                output_file_path = Path(output_path)

            # 确保目录存在
            output_file_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入TOML文件（使用tomli-w）
            with open(output_file_path, 'wb') as f:
                tomli_w.dump(export_data, f)

            logger.info(f"配置已导出到: {output_file_path} (层级结构: {use_hierarchy})")
            return str(output_file_path)

        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def _export_hierarchical(db: Session, include_sensitive: bool) -> Dict[str, Any]:
        """使用层级结构导出配置

        根据配置key中的点号(.)推断层级关系，例如:
        - exchange.name -> exchange: { name: value }
        - exchange.api.key -> exchange: { api: { key: value } }

        Args:
            db: 数据库会话
            include_sensitive: 是否包含敏感配置

        Returns:
            Dict[str, Any]: 层级结构的配置数据
        """
        # 按name分组构建层级结构
        config_groups: Dict[str, Dict[str, Any]] = {}

        # 获取所有配置
        all_configs = db.query(SystemConfig).all()

        for config in all_configs:
            group_name = str(config.name) if config.name else "general"

            if group_name not in config_groups:
                config_groups[group_name] = {}

            # 获取配置key
            config_key = str(config.key)

            # 如果key以group_name开头，去掉前缀避免重复
            # 例如: group_name="exchange", key="exchange.binance.name" -> "binance.name"
            if config_key.startswith(f"{group_name}."):
                config_key = config_key[len(group_name) + 1:]  # +1 for the dot

            # 处理敏感配置 - 总是导出，但敏感值设为空字符串
            if bool(config.is_sensitive):
                # 敏感配置导出为空字符串
                value = ""
                logger.info(f"导出敏感配置(值为空): {config.key}")
            else:
                # 解析配置值
                value = ConfigManager._parse_value(str(config.value))

            # 使用点号分隔的key构建嵌套结构
            ConfigManager._set_nested_value_with_description(
                config_groups[group_name],
                config_key,
                value,
                str(config.description) if config.description else ""
            )

        return config_groups
    
    @staticmethod
    def _set_nested_value_with_description(container: Dict, key: str, value: Any, description: str = ""):
        """将点号分隔的key转换为嵌套字典结构，支持描述信息
        
        Args:
            container: 目标容器字典
            key: 点号分隔的键名，如 "exchange.api.key"
            value: 配置值
            description: 配置描述
        """
        parts = key.split('.')
        current = container
        
        # 遍历所有部分，除了最后一个
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            # 如果当前部分是叶子节点（有_value），需要将其转换为嵌套结构
            elif isinstance(current[part], dict) and "_value" in current[part]:
                # 将叶子节点转换为中间节点，保留_value作为默认值
                old_value = current[part].pop("_value")
                old_desc = current[part].pop("_description", "")
                current[part]["_default"] = old_value
                if old_desc:
                    current[part]["_default_description"] = old_desc
            current = current[part]
        
        # 最后一个部分存储值和描述
        last_part = parts[-1]
        if description:
            current[last_part] = {
                "_value": value,
                "_description": description
            }
        else:
            current[last_part] = value
    
    @staticmethod
    def _export_flat(db: Session, include_sensitive: bool) -> Dict[str, Any]:
        """使用扁平化结构导出配置（兼容旧方式）
        
        Args:
            db: 数据库会话
            include_sensitive: 是否包含敏感配置
            
        Returns:
            Dict[str, Any]: 扁平化的配置数据
        """
        configs = db.query(SystemConfig).all()
        config_groups: Dict[str, Dict[str, Any]] = {}

        for config in configs:
            # 获取分组名称
            group_name = str(config.name) if config.name else "general"

            if group_name not in config_groups:
                config_groups[group_name] = {}

            # 处理敏感配置 - 总是导出，但敏感值设为空字符串
            if bool(config.is_sensitive):
                # 敏感配置导出为空字符串
                value = ""
                logger.info(f"导出敏感配置(值为空): {config.key}")
            else:
                # 解析配置值
                value = ConfigManager._parse_value(str(config.value))

            # 使用点号分隔的key转换为嵌套字典
            ConfigManager._set_nested_value(
                config_groups[group_name],
                str(config.key),
                value,
                str(config.description) if config.description else "",
                bool(config.is_sensitive)
            )

        return config_groups
    
    @staticmethod
    def import_from_toml(input_path: Optional[str] = None, 
                        overwrite: bool = True,
                        dry_run: bool = False) -> Dict[str, Any]:
        """从TOML文件导入系统配置
        
        Args:
            input_path: 输入文件路径，默认为项目根目录下的 config.toml
            overwrite: 是否覆盖已存在的配置
            dry_run: 是否为试运行模式（不实际写入数据库）
            
        Returns:
            Dict: 导入结果统计
        """
        init_database_config()
        db: Session = SessionLocal()
        
        try:
            # 确定输入路径
            if input_path is None:
                input_file_path: Path = project_root / "config.toml"
            else:
                input_file_path = Path(input_path)
            
            if not input_file_path.exists():
                raise FileNotFoundError(f"配置文件不存在: {input_file_path}")
            
            # 读取TOML文件（使用tomli）
            with open(input_file_path, 'rb') as f:
                data = tomli.load(f)
            
            # 移除元数据
            meta = data.pop('_meta', {})
            logger.info(f"导入配置文件: {input_file_path}, 导出时间: {meta.get('export_time', 'unknown')}")
            
            # 统计信息
            stats = {
                "total": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "details": []
            }
            
            # 遍历所有分组
            for group_name, group_config in data.items():
                if not isinstance(group_config, dict):
                    continue
                
                # 将嵌套字典扁平化
                flat_configs = ConfigManager._flatten_dict(group_config, group_name)
                
                for config_item in flat_configs:
                    stats["total"] += 1
                    key = config_item["key"]
                    value = config_item["value"]
                    description = config_item.get("description", "")
                    is_sensitive = config_item.get("is_sensitive", False)
                    
                    try:
                        if dry_run:
                            # 试运行模式，只记录日志
                            logger.info(f"[DRY RUN] 将导入配置: {key} = {value}")
                            stats["details"].append({"key": key, "action": "dry_run"})
                            continue
                        
                        # 检查配置是否已存在
                        existing = db.query(SystemConfig).filter_by(key=key).first()
                        
                        if existing and not overwrite:
                            logger.info(f"跳过已存在的配置: {key}")
                            stats["skipped"] += 1
                            stats["details"].append({"key": key, "action": "skipped"})
                            continue
                        
                        # 转换值为字符串
                        str_value = ConfigManager._value_to_string(value)
                        
                        if existing:
                            # 更新现有配置
                            existing.value = str_value
                            existing.description = description or existing.description
                            existing.is_sensitive = is_sensitive
                            action = "updated"
                            stats["updated"] += 1
                        else:
                            # 创建新配置
                            config = SystemConfig(
                                key=key,
                                value=str_value,
                                description=description,
                                name=group_name,
                                is_sensitive=is_sensitive
                            )
                            db.add(config)
                            action = "created"
                            stats["created"] += 1
                        
                        logger.info(f"配置已{action}: {key}")
                        stats["details"].append({"key": key, "action": action})
                        
                    except Exception as e:
                        logger.error(f"导入配置失败: {key}, error={e}")
                        stats["failed"] += 1
                        stats["details"].append({"key": key, "action": "failed", "error": str(e)})
            
            if not dry_run:
                db.commit()
                logger.info(f"配置导入完成: 总计={stats['total']}, 新建={stats['created']}, "
                          f"更新={stats['updated']}, 跳过={stats['skipped']}, 失败={stats['failed']}")
            
            return stats
            
        except Exception as e:
            if not dry_run:
                db.rollback()
            logger.error(f"导入配置失败: {e}")
            raise
        finally:
            db.close()
    
    @staticmethod
    def _parse_value(value: str) -> Any:
        """解析配置值，尝试转换为合适的数据类型
        
        Args:
            value: 字符串值
            
        Returns:
            Any: 解析后的值
        """
        if value is None:
            return None
        
        # 尝试解析为JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 尝试转换为布尔值
        if value.lower() == 'true' or value == '1':
            return True
        if value.lower() == 'false' or value == '0':
            return False
        
        # 尝试转换为整数
        try:
            return int(value)
        except ValueError:
            pass
        
        # 尝试转换为浮点数
        try:
            return float(value)
        except ValueError:
            pass
        
        # 保持为字符串
        return value
    
    @staticmethod
    def _value_to_string(value: Any) -> str:
        """将值转换为字符串存储
        
        Args:
            value: 任意类型的值
            
        Returns:
            str: 字符串表示
        """
        if value is None:
            return ""
        
        if isinstance(value, bool):
            return '1' if value else '0'
        
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        
        return str(value)
    
    @staticmethod
    def _set_nested_value(container: Dict, key: str, value: Any, 
                         description: str = "", is_sensitive: bool = False):
        """将点号分隔的key转换为嵌套字典结构
        
        Args:
            container: 目标容器字典
            key: 点号分隔的键名
            value: 配置值
            description: 配置描述
            is_sensitive: 是否敏感配置
        """
        parts = key.split('.')
        current = container
        
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # 最后一个部分存储值和元数据
        last_part = parts[-1]
        if description or is_sensitive:
            current[last_part] = {
                "_value": value,
                "_description": description,
                "_is_sensitive": is_sensitive
            }
        else:
            current[last_part] = value
    
    @staticmethod
    def _flatten_dict(nested_dict: Dict, group_name: str, prefix: str = "") -> List[Dict]:
        """将嵌套字典扁平化为配置项列表
        
        Args:
            nested_dict: 嵌套字典
            group_name: 分组名称
            prefix: 键名前缀
            
        Returns:
            List[Dict]: 扁平化的配置项列表
        """
        result = []
        
        for key, value in nested_dict.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                # 检查是否是特殊格式（包含_value等元数据）
                if "_value" in value:
                    result.append({
                        "key": full_key,
                        "value": value["_value"],
                        "description": value.get("_description", ""),
                        "is_sensitive": value.get("_is_sensitive", False)
                    })
                else:
                    # 递归处理嵌套字典
                    result.extend(ConfigManager._flatten_dict(value, group_name, full_key))
            else:
                result.append({
                    "key": full_key,
                    "value": value,
                    "description": "",
                    "is_sensitive": False
                })
        
        return result
    
    # ==================== JSON与TOML转换功能 ====================
    
    def to_json(self) -> str:
        """将配置转换为JSON字符串
        
        Returns:
            str: JSON格式的配置字符串
        """
        try:
            config_data = self.read_config()
            json_str = json.dumps(config_data, ensure_ascii=False, indent=2)
            logger.info("配置已转换为JSON格式")
            return json_str
        except Exception as e:
            logger.error(f"配置转JSON失败: {str(e)}")
            return "{}"
    
    def from_json(self, json_str: str) -> bool:
        """从JSON字符串加载配置
        
        Args:
            json_str: JSON格式的配置字符串
            
        Returns:
            bool: 加载成功返回True，失败返回False
        """
        try:
            config_data = json.loads(json_str)
            return self.write_config(config_data)
        except Exception as e:
            logger.error(f"JSON加载配置失败: {str(e)}")
            return False
    
    def json_to_toml(self, json_str: str, output_path: Optional[str] = None) -> Optional[str]:
        """将JSON字符串转换为TOML文件
        
        Args:
            json_str: JSON格式的配置字符串
            output_path: 输出TOML文件路径，默认为当前配置文件路径
            
        Returns:
            Optional[str]: 输出文件路径，失败返回None
        """
        try:
            # 解析JSON
            config_data = json.loads(json_str)
            
            # 确定输出路径
            if output_path is None:
                toml_path = self.config_path
            else:
                toml_path = Path(output_path)
            
            # 确保目录存在
            toml_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入TOML文件
            with open(toml_path, 'wb') as f:
                tomli_w.dump(config_data, f)
            
            logger.info(f"JSON已转换为TOML: {toml_path}")
            return str(toml_path)
            
        except Exception as e:
            logger.error(f"JSON转TOML失败: {str(e)}")
            return None
    
    def toml_to_json(self, input_path: Optional[str] = None) -> str:
        """将TOML文件转换为JSON字符串
        
        Args:
            input_path: 输入TOML文件路径，默认为当前配置文件路径
            
        Returns:
            str: JSON格式的配置字符串
        """
        try:
            # 确定输入路径
            if input_path is None:
                toml_path = self.config_path
            else:
                toml_path = Path(input_path)
            
            # 读取TOML文件
            with open(toml_path, 'rb') as f:
                config_data = tomli.load(f)
            
            # 转换为JSON字符串
            json_str = json.dumps(config_data, ensure_ascii=False, indent=2)
            
            logger.info(f"TOML已转换为JSON: {toml_path}")
            return json_str
            
        except Exception as e:
            logger.error(f"TOML转JSON失败: {str(e)}")
            return "{}"


# 创建全局配置管理器实例
config_manager = ConfigManager()


def load_system_configs() -> Dict[str, Any]:
    """加载系统配置

    从系统配置表中加载所有配置，返回扁平化的配置字典。
    用于应用启动时加载配置到上下文。

    Returns:
        Dict[str, Any]: 配置字典，key为配置键名，value为配置值
    """
    from collector.db.database import init_database_config, SessionLocal
    from collector.db.models import SystemConfig

    init_database_config()
    db = SessionLocal()

    try:
        configs = db.query(SystemConfig).all()
        result = {}
        for config in configs:
            # 敏感配置返回空字符串
            if bool(config.is_sensitive):
                result[config.key] = ""
            else:
                result[config.key] = config.value
        return result
    except Exception as e:
        logger.error(f"加载系统配置失败: {e}")
        return {}
    finally:
        db.close()


# 保持向后兼容的别名
ConfigIO = ConfigManager


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="系统配置管理工具")
    parser.add_argument("action", choices=["export", "import", "to-json", "to-toml"], help="操作类型")
    parser.add_argument("-f", "--file", help="TOML文件路径")
    parser.add_argument("--include-sensitive", action="store_true", 
                       help="导出时包含敏感配置")
    parser.add_argument("--overwrite", action="store_true", default=True,
                       help="导入时覆盖已存在的配置")
    parser.add_argument("--dry-run", action="store_true",
                       help="试运行模式，不实际写入数据库")
    
    args = parser.parse_args()
    
    try:
        if args.action == "export":
            output_path = ConfigManager.export_to_toml(args.file, args.include_sensitive)
            print(f"配置已导出到: {output_path}")
        elif args.action == "import":
            stats = ConfigManager.import_from_toml(args.file, args.overwrite, args.dry_run)
            print(f"导入完成: 总计={stats['total']}, 新建={stats['created']}, "
                  f"更新={stats['updated']}, 跳过={stats['skipped']}, 失败={stats['failed']}")
        elif args.action == "to-json":
            json_str = config_manager.toml_to_json(args.file)
            print(json_str)
        elif args.action == "to-toml":
            # 从stdin读取JSON
            import sys
            json_str = sys.stdin.read()
            output_path = config_manager.json_to_toml(json_str, args.file)
            if output_path:
                print(f"JSON已转换为TOML: {output_path}")
            else:
                print("转换失败")
                sys.exit(1)
    except Exception as e:
        print(f"操作失败: {e}")
        sys.exit(1)
