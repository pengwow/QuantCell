#!/usr/bin/env python3
"""
数据库初始化脚本

用于在程序安装过程中执行全量数据库表初始化操作
支持SQLite和DuckDB数据库
"""
import os
import sys
from pathlib import Path
import logging
import traceback
import json
from datetime import datetime
from typing import Optional, List

# 添加项目根目录到Python路径（必须在导入utils之前）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import typer
from typing_extensions import Annotated

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

from sqlalchemy import inspect

# 先导入基础模块，避免循环导入
from collector.db.database import init_database_config, Base

# 延迟导入模型，避免导入错误
SystemConfig = None
Task = None
Feature = None
DataPool = None
DataPoolAsset = None
CryptoSymbol = None
CryptoSpotKline = None
CryptoFutureKline = None
StockKline = None
ScheduledTask = None
BacktestTask = None
BacktestResult = None
Strategy = None

def load_models():
    """延迟加载模型，避免导入错误"""
    global SystemConfig, Task, Feature, DataPool, DataPoolAsset
    global CryptoSymbol, CryptoSpotKline, CryptoFutureKline, StockKline
    global ScheduledTask, BacktestTask, BacktestResult, Strategy
    
    from collector.db.models import (
        SystemConfig as SC,
        Task as T,
        Feature as F,
        DataPool as DP,
        DataPoolAsset as DPA,
        CryptoSymbol as CS,
        CryptoSpotKline as CSK,
        CryptoFutureKline as CFK,
        StockKline as SK,
        ScheduledTask as ST,
    )
    from backtest.models import BacktestTask as BT, BacktestResult as BR
    from strategy.models import Strategy as S
    
    SystemConfig = SC
    Task = T
    Feature = F
    DataPool = DP
    DataPoolAsset = DPA
    CryptoSymbol = CS
    CryptoSpotKline = CSK
    CryptoFutureKline = CFK
    StockKline = SK
    ScheduledTask = ST
    BacktestTask = BT
    BacktestResult = BR
    Strategy = S

def setup_logging():
    """设置日志配置
    
    注意：日志器已经由 UnifiedLogger 配置完成，
    这里只需要确保日志目录存在即可。
    """
    # 确保日志目录存在
    log_file = Path(__file__).parent.parent / "logs" / "init_database.log"
    log_file.parent.mkdir(exist_ok=True)
    logger.info(f"日志目录已准备: {log_file.parent}")

def get_strategy_files(strategies_dir: Path) -> List[Path]:
    """获取策略目录下的所有策略文件
    
    Args:
        strategies_dir: 策略目录路径
        
    Returns:
        List[Path]: 策略文件路径列表
    """
    if not strategies_dir.exists():
        logger.warning(f"策略目录不存在: {strategies_dir}")
        return []
    
    # 获取所有 .py 文件，排除 __init__.py 和私有文件
    strategy_files = [
        f for f in strategies_dir.glob("*.py")
        if f.name != "__init__.py" and not f.name.startswith("_")
    ]
    
    return sorted(strategy_files)

def parse_strategy_info(file_path: Path) -> dict:
    """解析策略文件信息
    
    Args:
        file_path: 策略文件路径
        
    Returns:
        dict: 策略信息字典
    """
    content = file_path.read_text(encoding="utf-8")
    
    # 提取模块文档字符串作为描述
    description = ""
    if '"""' in content:
        parts = content.split('"""')
        if len(parts) >= 3:
            description = parts[1].strip()
    
    # 提取策略名称（从文件名）
    name = file_path.stem
    
    # 尝试从代码中提取策略类名
    class_name = None
    for line in content.split("\n"):
        if "class " in line and "Strategy" in line and "(" in line:
            # 提取类名
            class_part = line.split("class ")[1].split("(")[0].strip()
            if class_part != "Strategy" and not class_part.startswith("_"):
                class_name = class_part
                break
    
    # 提取参数（从Config类）
    parameters = []
    in_config_class = False
    config_class_name = f"{name.replace('_', ' ').title().replace(' ', '')}Config"
    
    for line in content.split("\n"):
        if f"class {config_class_name}" in line or "class Config" in line:
            in_config_class = True
            continue
        
        if in_config_class:
            if line.strip().startswith("class ") and "Config" not in line:
                break
            if ":" in line and "=" in line and "#" not in line.split(":")[0]:
                # 可能是参数定义
                param_part = line.strip()
                if param_part and not param_part.startswith("#"):
                    # 简单提取参数名
                    param_name = param_part.split(":")[0].strip()
                    if param_name and not param_name.startswith("_"):
                        param_info = {
                            "name": param_name,
                            "type": "string",
                            "description": "",
                            "default": None
                        }
                        parameters.append(param_info)
    
    return {
        "name": name,
        "description": description[:500] if description else f"策略: {name}",
        "file_path": str(file_path),
        "file_name": file_path.name,
        "code": content,
        "parameters_json": json.dumps(parameters) if parameters else "[]",
        "version": "1.0.0",
        "tags_list": ["auto-import"],
        "strategy_type": "default",
        "status": "active",
        "class_name": class_name
    }

def init_strategies(
    strategies_dir: Optional[Path] = None,
    force_update: bool = False
) -> bool:
    """初始化策略，将策略文件写入策略表
    
    Args:
        strategies_dir: 策略目录路径，默认为 backend/strategies
        force_update: 是否强制更新已存在的策略
        
    Returns:
        bool: 是否成功
    """
    try:
        logger.info("开始初始化策略...")
        
        # 加载模型
        load_models()
        
        # 获取策略目录
        if strategies_dir is None:
            strategies_dir = Path(__file__).parent.parent / "strategies"
        
        strategy_files = get_strategy_files(strategies_dir)
        
        if not strategy_files:
            logger.warning(f"在 {strategies_dir} 中未找到策略文件")
            return True
        
        logger.info(f"找到 {len(strategy_files)} 个策略文件")
        
        # 导入数据库会话
        from collector.db.database import SessionLocal
        
        db = SessionLocal()
        try:
            imported_count = 0
            skipped_count = 0
            error_count = 0
            
            for file_path in strategy_files:
                try:
                    # 解析策略信息
                    strategy_info = parse_strategy_info(file_path)
                    name = strategy_info["name"]
                    
                    # 检查策略是否已存在
                    existing = db.query(Strategy).filter(Strategy.name == name).first()
                    
                    if existing and not force_update:
                        logger.info(f"策略已存在，跳过: {name}")
                        skipped_count += 1
                        continue
                    
                    if existing and force_update:
                        # 更新现有策略
                        existing.description = strategy_info["description"]
                        existing.file_path = strategy_info["file_path"]
                        existing.file_name = strategy_info["file_name"]
                        existing.code = strategy_info["code"]
                        existing.version = strategy_info["version"]
                        existing.tags = json.dumps(strategy_info["tags_list"])
                        existing.status = strategy_info["status"]
                        logger.info(f"更新策略: {name}")
                    else:
                        # 创建新策略
                        new_strategy = Strategy(
                            name=name,
                            description=strategy_info["description"],
                            file_path=strategy_info["file_path"],
                            file_name=strategy_info["file_name"],
                            code=strategy_info["code"],
                            version=strategy_info["version"],
                            tags=json.dumps(strategy_info["tags_list"]),
                            strategy_type=strategy_info["strategy_type"],
                            status=strategy_info["status"]
                        )
                        db.add(new_strategy)
                        logger.info(f"导入策略: {name}")
                    
                    imported_count += 1
                    
                except Exception as e:
                    logger.error(f"处理策略文件失败 {file_path}: {str(e)}")
                    error_count += 1
            
            db.commit()
            
            logger.info("策略初始化完成:")
            logger.info(f"  - 导入/更新: {imported_count}")
            logger.info(f"  - 跳过: {skipped_count}")
            logger.info(f"  - 错误: {error_count}")
            
            return error_count == 0
            
        except Exception as e:
            db.rollback()
            logger.error(f"策略初始化失败: {str(e)}")
            logger.error(traceback.format_exc())
            return False
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"策略初始化失败: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def init_database():
    """初始化数据库
    
    1. 初始化数据库配置
    2. 加载数据模型
    3. 创建所有表结构
    4. 处理数据库兼容性问题
    5. 记录执行结果
    """
    try:
        logger.info("开始数据库初始化...")
        
        # 初始化数据库配置
        init_database_config()
        logger.info("数据库配置初始化成功")
        
        # 加载数据模型
        logger.info("加载数据模型...")
        load_models()
        logger.info("数据模型加载成功")
        
        # 获取所有模型类
        models = [
            SystemConfig,
            Task,
            Feature,
            DataPool,
            DataPoolAsset,
            CryptoSymbol,
            CryptoSpotKline,
            CryptoFutureKline,
            StockKline,
            ScheduledTask,
            BacktestTask,
            BacktestResult,
            Strategy
        ]
        
        logger.info(f"找到 {len(models)} 个数据模型")
        
        # 创建表结构
        logger.info("开始创建数据库表结构...")
        from collector.db.database import engine
        Base.metadata.create_all(engine, checkfirst=True)
        logger.info("数据库表结构创建完成")
        
        # 验证表是否创建成功
        logger.info("验证表结构...")
        
        from collector.db.database import engine
        
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        logger.info(f"数据库中存在 {len(existing_tables)} 个表: {existing_tables}")
        
        # 检查关键表是否存在
        key_tables = ["system_config", "crypto_symbols", "crypto_spot_klines"]
        for table in key_tables:
            if table in existing_tables:
                logger.info(f"关键表 {table} 存在")
            else:
                logger.warning(f"关键表 {table} 不存在")
        
        # 检查crypto_symbols表是否有is_deleted字段
        if "crypto_symbols" in existing_tables:
            columns = [col['name'] for col in inspector.get_columns("crypto_symbols")]
            if "is_deleted" in columns:
                logger.info("crypto_symbols表已包含is_deleted字段")
            else:
                logger.warning("crypto_symbols表缺少is_deleted字段，建议运行迁移脚本")
        
        # 将config.toml配置写入系统配置表
        logger.info("开始写入配置到系统配置表...")
        try:
            # 导入配置管理器
            
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from utils.config_manager import config_manager
            from settings.models import SystemConfigBusiness
            
            # 使用配置管理器读取配置文件
            config_data = config_manager.read_config()
            
            logger.info("读取到配置文件")
            
            # 定义配置分组映射
            config_group_mapping = {
                'database': 'database',
                'app': 'app',
                'quant': 'quant',
                'basic_settings': 'basic',
                'notification_settings': 'notifications',
                'api_settings': 'api',
                'system_config': 'system'
            }
            
            # 遍历所有配置分组
            for group_name, group_config in config_data.items():
                # 检查是否为嵌套分组（如exchanges.binance）
                if isinstance(group_config, dict):
                    # 检查是否需要特殊处理
                    if group_name in config_group_mapping:
                        # 使用映射的分组名称
                        mapped_group = config_group_mapping[group_name]
                        logger.info(f"处理配置分组: {group_name} -> {mapped_group}")
                        
                        # 遍历分组内的配置项
                        for key, value in group_config.items():
                            # 检查value是否为嵌套字典（如exchanges.binance）
                            if isinstance(value, dict):
                                # 处理嵌套分组
                                for nested_key, nested_value in value.items():
                                    # 直接使用原始key，不进行拼接
                                    SystemConfigBusiness.set(nested_key, str(nested_value), name=group_name)
                                    logger.debug(f"写入配置项: {nested_key} = {nested_value} (name={group_name})")
                            else:
                                # 处理普通配置项
                                # 直接使用原始key，不进行拼接
                                SystemConfigBusiness.set(key, str(value), name=group_name)
                                logger.debug(f"写入配置项: {key} = {value} (name={group_name})")
                        
                        logger.info(f"{group_name}配置写入完成")
                    else:
                        # 处理未映射的分组
                        logger.info(f"处理未映射的配置分组: {group_name}")
                        
                        # 遍历分组内的配置项
                        for key, value in group_config.items():
                            # 直接使用原始key，不进行拼接
                            SystemConfigBusiness.set(key, str(value), name=group_name)
                            logger.debug(f"写入配置项: {key} = {value} (name={group_name})")
                        
                        logger.info(f"{group_name}配置写入完成")
            
            logger.info("配置写入系统配置表完成")
        except Exception as e:
            logger.error(f"写入配置到系统配置表失败: {str(e)}")
            logger.error(traceback.format_exc())
        
        logger.info("数据库初始化完成！")
        return True
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        logger.error(traceback.format_exc())
        return False

# ==================== Agent 工具参数初始化 ====================

# 工具参数模板定义（与 agent/config/templates.py 中的 param_template 保持一致）
AGENT_TOOL_PARAMS_TEMPLATES = {
    "web_search": {
        "api_key": {
            "type": "string",
            "required": True,
            "sensitive": True,
            "default": "",
            "env_key": "BRAVE_API_KEY",
            "description": "Brave Search API 密钥"
        },
        "max_results": {
            "type": "integer",
            "required": False,
            "default": 5,
            "env_key": None,
            "description": "最大搜索结果数量 (1-10)",
            "validation": {"min": 1, "max": 10}
        },
        "proxy": {
            "type": "string",
            "required": False,
            "default": None,
            "env_key": None,
            "description": "HTTP/SOCKS5代理地址 (如 http://127.0.0.1:7890)"
        }
    },
    "web_fetch": {
        "max_chars": {
            "type": "integer",
            "required": False,
            "default": 50000,
            "env_key": None,
            "description": "最大提取字符数"
        },
        "proxy": {
            "type": "string",
            "required": False,
            "default": None,
            "env_key": None,
            "description": "HTTP/SOCKS5代理地址 (如 http://127.0.0.1:7890)"
        }
    },
    "exec": {
        "timeout": {
            "type": "integer",
            "required": False,
            "default": 60,
            "env_key": None,
            "description": "命令执行超时时间（秒）",
            "validation": {"min": 1, "max": 300}
        },
        "path_append": {
            "type": "string",
            "required": False,
            "default": "",
            "env_key": None,
            "description": "附加到PATH环境变量的路径"
        }
    },
    "read_file": {
        "default_limit": {
            "type": "integer",
            "required": False,
            "default": 200,
            "env_key": None,
            "description": "默认读取行数",
            "validation": {"min": 1, "max": 500}
        }
    }
}


def init_agent_tool_params(
    force_update: bool = False
) -> bool:
    """
    初始化Agent工具参数配置
    
    将工具参数默认值写入数据库system_config表，
    用户可以通过Web界面或CLI进行修改。
    
    Args:
        force_update: 是否强制更新已有参数
        
    Returns:
        bool: 是否成功
    """
    try:
        logger.info("开始初始化Agent工具参数...")
        
        # 确保数据库配置已初始化（即使跳过表创建）
        init_database_config()
        
        # 使用engine直接操作（避免Session绑定问题）
        from collector.db.database import engine
        from sqlalchemy import text as sa_text
        
        if engine is None:
            logger.error("数据库引擎未初始化，请先运行 --init-db 初始化数据库")
            return False
        
        imported_count = 0
        skipped_count = 0
        error_count = 0
            
        for tool_name, params in AGENT_TOOL_PARAMS_TEMPLATES.items():
            for param_name, param_def in params.items():
                try:
                    db_key = f"agent.tools.{tool_name}.{param_name}"
                    
                    # 检查是否已存在
                    with engine.connect() as conn:
                        result = conn.execute(
                            sa_text("SELECT value FROM system_config WHERE key = :key"),
                            {"key": db_key}
                        )
                        existing_row = result.fetchone()
                        
                        if existing_row and not force_update:
                            skipped_count += 1
                            continue
                        
                        # 获取默认值（优先使用环境变量）
                        default_value = param_def.get("default")
                        env_key = param_def.get("env_key")
                        
                        if env_key and os.environ.get(env_key):
                            value = str(os.environ.get(env_key))
                            source = f"环境变量 ({env_key})"
                        elif default_value is not None:
                            value = str(default_value)
                            source = "默认值"
                        else:
                            value = ""
                            source = "空值"
                        
                        is_sensitive = 1 if param_def.get("sensitive") else 0
                        description = param_def.get("description", "")
                        
                        if existing_row and force_update:
                            # 更新现有记录
                            conn.execute(
                                sa_text("""
                                    UPDATE system_config
                                    SET value = :value,
                                        description = :desc,
                                        plugin = 'agent',
                                        name = :tool_name,
                                        is_sensitive = :sensitive,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE key = :key
                                """),
                                {
                                    "value": value,
                                    "desc": description,
                                    "tool_name": tool_name,
                                    "sensitive": is_sensitive,
                                    "key": db_key
                                }
                            )
                            logger.info(f"更新参数: {db_key} = {source}")
                        else:
                            # 创建新记录
                            conn.execute(
                                sa_text("""
                                    INSERT INTO system_config
                                    (key, value, description, plugin, name, is_sensitive, created_at, updated_at)
                                    VALUES (:key, :value, :desc, :plugin, :name, :sensitive, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                                """),
                                {
                                    "key": db_key,
                                    "value": value,
                                    "desc": description,
                                    "plugin": "agent",
                                    "name": tool_name,
                                    "sensitive": is_sensitive
                                }
                            )
                            logger.info(f"创建参数: {db_key} = {source}")
                        
                        conn.commit()
                        imported_count += 1
                        
                except Exception as e:
                    logger.error(f"处理参数失败 {tool_name}.{param_name}: {e}")
                    error_count += 1
            
            logger.info("Agent工具参数初始化完成:")
            logger.info(f"  - 导入/更新: {imported_count}")
            logger.info(f"  - 跳过: {skipped_count}")
            logger.info(f"  - 错误: {error_count}")
            
            return error_count == 0
            
    except Exception as e:
        logger.error(f"Agent工具参数初始化失败: {e}")
        logger.error(traceback.format_exc())
        return False


def check_agent_tool_params() -> dict:
    """
    检查数据库中已有的工具参数状态
    
    Returns:
        dict: 统计信息
    """
    try:
        from collector.db.database import SessionLocal
        from collector.db.models import SystemConfig
        
        init_database_config()
        db = SessionLocal()
        
        configs = db.query(SystemConfig).filter(
            SystemConfig.key.like('agent.tools.%')
        ).all()
        
        result = {
            "total_params": len(configs),
            "tools_with_params": set(),
            "configured_params": 0,
            "details": []
        }
        
        for c in configs:
            tool_name = c.name or "unknown"
            result["tools_with_params"].add(tool_name)
            if c.value and c.value.strip():  # 非空值视为已配置
                result["configured_params"] += 1
            
            result["details"].append({
                "key": c.key,
                "has_value": bool(c.value and c.value.strip()),
                "is_sensitive": c.is_sensitive,
                "tool": tool_name
            })
        
        db.close()
        
        return result
        
    except Exception as e:
        logger.error(f"检查工具参数状态失败: {e}")
        return {"error": str(e)}


# 创建 Typer 应用
app = typer.Typer(
    name="init-database",
    help="数据库初始化脚本 - 用于在程序安装过程中执行全量数据库表初始化操作",
    add_completion=False,
)

@app.command()
def main(
    init_db: Annotated[bool, typer.Option(
        "--init-db/--no-init-db",
        help="是否初始化数据库表结构",
        show_default=True,
    )] = True,
    init_strategy: Annotated[bool, typer.Option(
        "--init-strategy/--no-init-strategy",
        help="是否初始化策略（将策略文件导入策略表）",
        show_default=True,
    )] = False,
    strategies_dir: Annotated[Optional[Path], typer.Option(
        "--strategies-dir",
        help="策略目录路径，默认为 backend/strategies",
        exists=True,
        file_okay=False,
        dir_okay=True,
    )] = None,
    force_update: Annotated[bool, typer.Option(
        "--force-update/--no-force-update",
        help="强制更新已存在的策略或参数",
        show_default=True,
    )] = False,
    init_agent_params: Annotated[bool, typer.Option(
        "--init-agent-params/--no-init-agent-params",
        help="是否初始化Agent工具参数（将默认参数写入数据库）",
        show_default=True,
    )] = True,
):
    """数据库初始化脚本
    
    用于在程序安装过程中执行全量数据库表初始化操作，支持SQLite和DuckDB数据库。
    可选导入策略文件到策略表、初始化Agent工具参数配置。
    
    示例:
        python init_database.py                              # 初始化全部（数据库+策略+工具参数）
        python init_database.py --no-init-strategy              # 仅初始化数据库和工具参数
        python init_database.py --init-strategy --force-update   # 强制更新策略
        python init_database.py --force-update --init-agent-params  # 强制更新所有配置
    """
    setup_logging()
    
    logger.info("=====================================")
    logger.info("        数据库初始化脚本")
    logger.info("=====================================")
    
    # 显示当前配置
    logger.info(f"当前工作目录: {os.getcwd()}")
    logger.info(f"脚本路径: {Path(__file__).absolute()}")
    logger.info(f"初始化数据库: {init_db}")
    logger.info(f"初始化策略: {init_strategy}")
    logger.info(f"初始化工具参数: {init_agent_params}")
    if strategies_dir:
        logger.info(f"策略目录: {strategies_dir}")
    logger.info(f"强制更新: {force_update}")
    
    success = True
    
    # 初始化数据库
    if init_db:
        success = init_database() and success
    
    # 初始化策略
    if init_strategy and success:
        success = init_strategies(strategies_dir, force_update) and success
    
    # 初始化Agent工具参数
    if init_agent_params and success:
        success = init_agent_tool_params(force_update) and success
        
        # 显示初始化后的状态统计
        if success:
            stats = check_agent_tool_params()
            if "error" not in stats:
                logger.info("Agent工具参数状态:")
                logger.info(f"  - 总参数数: {stats.get('total_params', 0)}")
                logger.info(f"  - 涉及工具数: {len(stats.get('tools_with_params', []))}")
                logger.info(f"  - 已配置数: {stats.get('configured_params', 0)}")
    
    if success:
        logger.info("=====================================")
        logger.info("        初始化成功！")
        logger.info("=====================================")
        sys.exit(0)
    else:
        logger.error("=====================================")
        logger.error("        初始化失败！")
        logger.error("=====================================")
        sys.exit(1)

if __name__ == "__main__":
    app()
