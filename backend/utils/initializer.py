#!/usr/bin/env python3
"""
项目初始化协调模块

提供一键式项目环境初始化功能，协调配置导入、数据库初始化、迁移等步骤
"""

import sys
from typing import Dict, List, Optional, Callable
from datetime import datetime
from pathlib import Path

from utils.logger import get_logger, LogType
from utils.env_checker import EnvChecker
from utils.config_manager import ConfigManager as ConfigIO

logger = get_logger(__name__, LogType.APPLICATION)


class InitializationStep:
    """初始化步骤类"""
    
    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        required: bool = True,
        skippable: bool = False
    ):
        self.name = name
        self.description = description
        self.func = func
        self.required = required
        self.skippable = skippable
        self.status = "pending"  # pending, running, success, failed, skipped
        self.message = ""
        self.start_time = None
        self.end_time = None
    
    def execute(self, *args, **kwargs) -> bool:
        """执行步骤"""
        self.status = "running"
        self.start_time = datetime.now()
        
        try:
            result = self.func(*args, **kwargs)
            self.status = "success" if result else "failed"
            self.message = "执行成功" if result else "执行失败"
            return result
        except Exception as e:
            self.status = "failed"
            self.message = f"执行异常: {str(e)}"
            logger.error(f"步骤 {self.name} 执行失败: {e}")
            return False
        finally:
            self.end_time = datetime.now()
    
    def skip(self, reason: str = ""):
        """跳过步骤"""
        self.status = "skipped"
        self.message = reason or "已跳过"
        self.start_time = datetime.now()
        self.end_time = datetime.now()


class ProjectInitializer:
    """项目初始化器
    
    协调执行项目环境初始化的各个步骤
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.steps: List[InitializationStep] = []
        self.results: Dict = {}
        self.start_time = None
        self.end_time = None
        
        # 初始化步骤列表
        self._init_steps()
    
    def _init_steps(self):
        """初始化步骤列表"""
        self.steps = [
            InitializationStep(
                name="env_check",
                description="环境依赖检查",
                func=self._step_env_check,
                required=True,
                skippable=False
            ),
            InitializationStep(
                name="config_import",
                description="配置文件导入",
                func=self._step_config_import,
                required=False,
                skippable=True
            ),
            InitializationStep(
                name="db_init",
                description="数据库表初始化",
                func=self._step_db_init,
                required=True,
                skippable=False
            ),
            InitializationStep(
                name="db_migrate",
                description="数据库迁移",
                func=self._step_db_migrate,
                required=True,
                skippable=False
            ),
            InitializationStep(
                name="data_seed",
                description="初始数据填充",
                func=self._step_data_seed,
                required=False,
                skippable=True
            ),
            InitializationStep(
                name="verification",
                description="初始化结果验证",
                func=self._step_verification,
                required=True,
                skippable=False
            ),
        ]
    
    def _step_env_check(self) -> bool:
        """环境检查步骤"""
        logger.info("执行环境检查...")
        results = EnvChecker.check_all()
        
        if self.verbose:
            EnvChecker.print_report(results)
        
        return results["overall"]
    
    def _step_config_import(self, config_path: Optional[str] = None, **kwargs) -> bool:
        """配置导入步骤"""
        if not config_path:
            logger.info("未提供配置文件，跳过配置导入")
            return True
        
        logger.info(f"导入配置文件: {config_path}")
        
        try:
            stats = ConfigIO.import_from_toml(
                input_path=config_path,
                overwrite=True,
                dry_run=False
            )
            
            logger.info(
                f"配置导入完成: 总计={stats['total']}, "
                f"新建={stats['created']}, 更新={stats['updated']}, "
                f"跳过={stats['skipped']}, 失败={stats['failed']}"
            )
            
            return stats["failed"] == 0
        except Exception as e:
            logger.error(f"配置导入失败: {e}")
            return False
    
    def _step_db_init(self) -> bool:
        """数据库初始化步骤"""
        logger.info("初始化数据库表结构...")
        
        try:
            # 复用 init_database.py 中的逻辑
            from scripts.init_database import init_database
            init_database()
            logger.info("数据库表初始化完成")
            return True
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            return False
    
    def _step_db_migrate(self, revision: str = "head") -> bool:
        """数据库迁移步骤"""
        logger.info(f"执行数据库迁移到版本: {revision}")
        
        try:
            # 使用 Alembic API 执行迁移
            from alembic.config import Config
            from alembic import command
            
            # 加载 Alembic 配置
            alembic_cfg = Config("alembic.ini")
            
            # 执行升级
            command.upgrade(alembic_cfg, revision)
            
            logger.info("数据库迁移完成")
            return True
        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")
            return False
    
    def _step_data_seed(self) -> bool:
        """初始数据填充步骤"""
        logger.info("填充初始数据...")
        
        try:
            # 填充默认配置
            self._seed_default_configs()
            
            logger.info("初始数据填充完成")
            return True
        except Exception as e:
            logger.error(f"初始数据填充失败: {e}")
            return False
    
    def _seed_default_configs(self):
        """填充默认配置"""
        from collector.db.models import SystemConfig
        
        # 默认配置列表
        default_configs = [
            {
                "key": "theme",
                "value": "light",
                "name": "general",
                "description": "系统主题设置"
            },
            {
                "key": "language",
                "value": "zh-CN",
                "name": "general",
                "description": "系统语言设置"
            },
            {
                "key": "defaultPerPage",
                "value": "10",
                "name": "general",
                "description": "列表页默认显示数量"
            },
            {
                "key": "timezone",
                "value": "Asia/Shanghai",
                "name": "general",
                "description": "系统默认时区"
            },
            {
                "key": "showTips",
                "value": "true",
                "name": "general",
                "description": "是否显示提示"
            },
        ]
        
        for config in default_configs:
            existing = SystemConfig.get(config["key"])
            if existing is None:
                SystemConfig.set(**config)
                logger.info(f"创建默认配置: {config['key']}")
    
    def _step_verification(self) -> bool:
        """验证步骤"""
        logger.info("验证初始化结果...")
        
        try:
            # 检查数据库连接
            from collector.db.database import SessionLocal, init_database_config
            init_database_config()
            db = SessionLocal()
            
            # 执行简单查询
            from sqlalchemy import text
            result = db.execute(text("SELECT COUNT(*) FROM system_configs"))
            count = result.fetchone()[0]
            
            db.close()
            
            logger.info(f"验证通过，系统配置表中有 {count} 条记录")
            return True
        except Exception as e:
            logger.error(f"验证失败: {e}")
            return False
    
    def run(
        self,
        config_path: Optional[str] = None,
        skip_config_import: bool = False,
        skip_data_seed: bool = False,
        migrate_revision: str = "head"
    ) -> Dict:
        """执行初始化流程
        
        Args:
            config_path: 配置文件路径
            skip_config_import: 是否跳过配置导入
            skip_data_seed: 是否跳过数据填充
            migrate_revision: 迁移目标版本
            
        Returns:
            Dict: 初始化结果
        """
        self.start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("开始项目环境初始化")
        logger.info("=" * 60)
        
        success = True
        
        for step in self.steps:
            # 检查是否需要跳过
            if step.name == "config_import" and skip_config_import:
                step.skip("用户指定跳过")
                logger.info(f"跳过步骤: {step.description}")
                continue
            
            if step.name == "data_seed" and skip_data_seed:
                step.skip("用户指定跳过")
                logger.info(f"跳过步骤: {step.description}")
                continue
            
            # 执行步骤
            logger.info(f"执行步骤: {step.description}")
            
            if step.name == "config_import":
                result = step.execute(config_path=config_path)
            elif step.name == "db_migrate":
                result = step.execute(revision=migrate_revision)
            else:
                result = step.execute()
            
            if not result and step.required:
                success = False
                logger.error(f"必要步骤失败: {step.description}")
                break
            
            if self.verbose:
                status_icon = "✓" if step.status == "success" else "○" if step.status == "skipped" else "✗"
                logger.info(f"{status_icon} {step.description}: {step.message}")
        
        self.end_time = datetime.now()
        
        # 生成结果报告
        self.results = self._generate_report(success)
        
        if success:
            logger.info("=" * 60)
            logger.info("项目环境初始化完成")
            logger.info("=" * 60)
        else:
            logger.error("=" * 60)
            logger.error("项目环境初始化失败")
            logger.error("=" * 60)
        
        return self.results
    
    def _generate_report(self, success: bool) -> Dict:
        """生成初始化报告
        
        Args:
            success: 是否成功
            
        Returns:
            Dict: 报告数据
        """
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        
        report = {
            "success": success,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": duration,
            "steps": [],
        }
        
        for step in self.steps:
            step_duration = 0
            if step.start_time and step.end_time:
                step_duration = (step.end_time - step.start_time).total_seconds()
            
            report["steps"].append({
                "name": step.name,
                "description": step.description,
                "status": step.status,
                "message": step.message,
                "duration_seconds": step_duration,
            })
        
        return report
    
    def print_report(self):
        """打印初始化报告"""
        print("\n" + "=" * 60)
        print("项目初始化报告")
        print("=" * 60)
        
        for step in self.results.get("steps", []):
            status_icon = {
                "success": "✓",
                "failed": "✗",
                "skipped": "○",
                "pending": "•",
                "running": "⟳"
            }.get(step["status"], "?")
            
            print(f"\n{status_icon} {step['description']}")
            print(f"   状态: {step['status']}")
            if step['message']:
                print(f"   信息: {step['message']}")
            if step['duration_seconds'] > 0:
                print(f"   耗时: {step['duration_seconds']:.2f}s")
        
        print("\n" + "=" * 60)
        if self.results.get("success"):
            print(f"✓ 初始化成功 (总耗时: {self.results['duration_seconds']:.2f}s)")
        else:
            print(f"✗ 初始化失败 (总耗时: {self.results['duration_seconds']:.2f}s)")
        print("=" * 60 + "\n")


# 便捷函数
def setup_project(
    config_path: Optional[str] = None,
    skip_config_import: bool = False,
    skip_data_seed: bool = False,
    migrate_revision: str = "head",
    verbose: bool = False
) -> Dict:
    """便捷函数：一键设置项目
    
    Args:
        config_path: 配置文件路径
        skip_config_import: 是否跳过配置导入
        skip_data_seed: 是否跳过数据填充
        migrate_revision: 迁移目标版本
        verbose: 是否输出详细信息
        
    Returns:
        Dict: 初始化结果
    """
    initializer = ProjectInitializer(verbose=verbose)
    results = initializer.run(
        config_path=config_path,
        skip_config_import=skip_config_import,
        skip_data_seed=skip_data_seed,
        migrate_revision=migrate_revision
    )
    
    if verbose:
        initializer.print_report()
    
    return results


if __name__ == "__main__":
    # 命令行测试
    results = setup_project(verbose=True)
    sys.exit(0 if results["success"] else 1)
