#!/usr/bin/env python3
"""
系统配置导入导出工具

支持将系统配置表导出为TOML文件，以及从TOML文件导入配置
"""

import os
import sys
import json
import toml
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


class ConfigIO:
    """系统配置导入导出类
    
    提供配置的导入导出功能，支持TOML格式
    """
    
    @staticmethod
    def export_to_toml(output_path: Optional[str] = None, include_sensitive: bool = False) -> str:
        """将系统配置导出为TOML文件
        
        Args:
            output_path: 输出文件路径，默认为项目根目录下的 config.toml
            include_sensitive: 是否包含敏感配置（密码等）
            
        Returns:
            str: 导出的文件路径
        """
        init_database_config()
        db: Session = SessionLocal()
        
        try:
            # 查询所有配置
            configs = db.query(SystemConfig).all()
            
            # 按name分组组织配置
            config_groups: Dict[str, Dict[str, Any]] = {}
            
            for config in configs:
                # 跳过敏感配置（除非明确指定包含）
                if config.is_sensitive and not include_sensitive:
                    logger.info(f"跳过敏感配置: {config.key}")
                    continue
                
                # 获取分组名称
                group_name = config.name or "general"
                
                if group_name not in config_groups:
                    config_groups[group_name] = {}
                
                # 解析配置值
                value = ConfigIO._parse_value(config.value)
                
                # 使用点号分隔的key转换为嵌套字典
                ConfigIO._set_nested_value(
                    config_groups[group_name], 
                    config.key, 
                    value,
                    config.description,
                    config.is_sensitive
                )
            
            # 添加导出元数据
            export_data = {
                "_meta": {
                    "export_time": datetime.now().isoformat(),
                    "version": "1.0",
                    "total_configs": len(configs),
                    "include_sensitive": include_sensitive
                }
            }
            export_data.update(config_groups)
            
            # 确定输出路径
            if output_path is None:
                output_path = project_root / "config.toml"
            else:
                output_path = Path(output_path)
            
            # 确保目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入TOML文件
            with open(output_path, 'w', encoding='utf-8') as f:
                toml.dump(export_data, f)
            
            logger.info(f"配置已导出到: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            raise
        finally:
            db.close()
    
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
                input_path = project_root / "config.toml"
            else:
                input_path = Path(input_path)
            
            if not input_path.exists():
                raise FileNotFoundError(f"配置文件不存在: {input_path}")
            
            # 读取TOML文件
            with open(input_path, 'r', encoding='utf-8') as f:
                data = toml.load(f)
            
            # 移除元数据
            meta = data.pop('_meta', {})
            logger.info(f"导入配置文件: {input_path}, 导出时间: {meta.get('export_time', 'unknown')}")
            
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
                flat_configs = ConfigIO._flatten_dict(group_config, group_name)
                
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
                        str_value = ConfigIO._value_to_string(value)
                        
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
                    result.extend(ConfigIO._flatten_dict(value, group_name, full_key))
            else:
                result.append({
                    "key": full_key,
                    "value": value,
                    "description": "",
                    "is_sensitive": False
                })
        
        return result


# 命令行接口
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="系统配置导入导出工具")
    parser.add_argument("action", choices=["export", "import"], help="操作类型")
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
            output_path = ConfigIO.export_to_toml(args.file, args.include_sensitive)
            print(f"配置已导出到: {output_path}")
        elif args.action == "import":
            stats = ConfigIO.import_from_toml(args.file, args.overwrite, args.dry_run)
            print(f"导入完成: 总计={stats['total']}, 新建={stats['created']}, "
                  f"更新={stats['updated']}, 跳过={stats['skipped']}, 失败={stats['failed']}")
    except Exception as e:
        print(f"操作失败: {e}")
        sys.exit(1)
