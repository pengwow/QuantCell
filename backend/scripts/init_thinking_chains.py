#!/usr/bin/env python3
"""
初始化思维链配置脚本

导入默认的策略生成思维链和指标生成思维链配置到数据库。

使用方法:
    cd /Users/liupeng/workspace/quant/QuantCell/backend
    python scripts/init_thinking_chains.py
"""

import sys
from pathlib import Path

# 添加backend到Python路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 设置正确的数据库文件路径
import os
data_dir = backend_dir / "data"
os.environ["DB_FILE"] = str(data_dir / "quantcell_sqlite.db")

# 先初始化数据库配置
from collector.db.database import init_database_config
init_database_config()

from ai_model.thinking_chain import ThinkingChainManager
from loguru import logger


def init_thinking_chains():
    """初始化默认思维链配置"""
    manager = ThinkingChainManager()
    
    # 配置文件路径
    config_dir = backend_dir / "ai_model" / "prompts" / "templates"
    
    configs = [
        {
            "file": config_dir / "thinking_chain_config.toml",
            "name": "策略生成思维链"
        },
        {
            "file": config_dir / "indicator_thinking_chain_config.toml",
            "name": "指标生成思维链"
        }
    ]
    
    success_count = 0
    
    for config in configs:
        try:
            if not config["file"].exists():
                logger.warning(f"配置文件不存在: {config['file']}")
                continue
            
            # 读取TOML文件
            with open(config["file"], "r", encoding="utf-8") as f:
                toml_content = f.read()
            
            # 导入思维链
            result = manager.import_from_toml(toml_content, update_existing=True)
            
            if result.get("success"):
                logger.info(f"✅ {config['name']} 初始化成功")
                logger.info(f"   - 创建: {result.get('created', 0)} 条")
                logger.info(f"   - 更新: {result.get('updated', 0)} 条")
                success_count += 1
            else:
                logger.error(f"❌ {config['name']} 初始化失败: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"❌ {config['name']} 初始化异常: {e}")
    
    logger.info(f"\n初始化完成: {success_count}/{len(configs)} 个思维链配置")
    return success_count == len(configs)


if __name__ == "__main__":
    logger.info("开始初始化思维链配置...")
    
    try:
        success = init_thinking_chains()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"初始化过程发生错误: {e}")
        sys.exit(1)
