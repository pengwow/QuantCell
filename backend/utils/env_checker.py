#!/usr/bin/env python3
"""
环境检查模块

提供项目环境依赖检查功能，包括Python版本、数据库连接、依赖包等
"""

import sys
import subprocess
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class EnvChecker:
    """环境检查类
    
    检查项目运行所需的环境依赖是否满足
    """
    
    # 必需的Python版本
    REQUIRED_PYTHON_VERSION = (3, 8)
    
    # 必需的依赖包
    REQUIRED_PACKAGES = [
        "typer",
        "sqlalchemy",
        "alembic",
        "toml",
        "fastapi",
        "pydantic",
    ]
    
    # 可选的依赖包
    OPTIONAL_PACKAGES = [
        "redis",
        "celery",
        "pandas",
        "numpy",
    ]
    
    @staticmethod
    def check_python_version() -> Tuple[bool, str]:
        """检查Python版本
        
        Returns:
            Tuple[bool, str]: (是否满足要求, 版本信息)
        """
        current_version = sys.version_info[:2]
        required_version = EnvChecker.REQUIRED_PYTHON_VERSION
        
        if current_version >= required_version:
            return True, f"Python {current_version[0]}.{current_version[1]} (要求 >= {required_version[0]}.{required_version[1]})"
        else:
            return False, f"Python {current_version[0]}.{current_version[1]} (要求 >= {required_version[0]}.{required_version[1]})"
    
    @staticmethod
    def check_package_installed(package_name: str) -> Tuple[bool, Optional[str]]:
        """检查包是否已安装
        
        Args:
            package_name: 包名
            
        Returns:
            Tuple[bool, Optional[str]]: (是否安装, 版本号)
        """
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", package_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # 解析版本号
                for line in result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        version = line.split(':')[1].strip()
                        return True, version
                return True, None
            else:
                return False, None
        except Exception as e:
            logger.warning(f"检查包 {package_name} 失败: {e}")
            return False, None
    
    @staticmethod
    def check_all_packages() -> Dict[str, Dict]:
        """检查所有依赖包
        
        Returns:
            Dict[str, Dict]: 包检查结果
        """
        results = {
            "required": {},
            "optional": {},
        }
        
        # 检查必需包
        for package in EnvChecker.REQUIRED_PACKAGES:
            installed, version = EnvChecker.check_package_installed(package)
            results["required"][package] = {
                "installed": installed,
                "version": version,
            }
        
        # 检查可选包
        for package in EnvChecker.OPTIONAL_PACKAGES:
            installed, version = EnvChecker.check_package_installed(package)
            results["optional"][package] = {
                "installed": installed,
                "version": version,
            }
        
        return results
    
    @staticmethod
    def check_database_connection() -> Tuple[bool, str]:
        """检查数据库连接
        
        Returns:
            Tuple[bool, str]: (是否连接成功, 状态信息)
        """
        try:
            from collector.db.database import SessionLocal, init_database_config
            
            init_database_config()
            db = SessionLocal()
            
            # 执行简单查询测试连接
            from sqlalchemy import text
            result = db.execute(text("SELECT 1"))
            result.fetchone()
            
            db.close()
            return True, "数据库连接正常"
        except Exception as e:
            return False, f"数据库连接失败: {str(e)}"
    
    @staticmethod
    def check_config_file(config_path: Optional[str] = None) -> Tuple[bool, str]:
        """检查配置文件
        
        Args:
            config_path: 配置文件路径，默认检查常见位置
            
        Returns:
            Tuple[bool, str]: (是否存在, 状态信息)
        """
        if config_path:
            path = Path(config_path)
            if path.exists():
                return True, f"配置文件存在: {path}"
            else:
                return False, f"配置文件不存在: {path}"
        
        # 检查默认位置
        default_paths = [
            Path("config.toml"),
            Path("backend/config.toml"),
            Path("/etc/quantcell/config.toml"),
        ]
        
        for path in default_paths:
            if path.exists():
                return True, f"配置文件存在: {path}"
        
        return False, "未找到配置文件（检查默认位置）"
    
    @staticmethod
    def check_all() -> Dict[str, any]:
        """执行所有环境检查
        
        Returns:
            Dict: 完整的检查结果
        """
        logger.info("开始环境检查...")
        
        results = {
            "python": {},
            "packages": {},
            "database": {},
            "config": {},
            "overall": False,
        }
        
        # 检查Python版本
        python_ok, python_info = EnvChecker.check_python_version()
        results["python"] = {
            "ok": python_ok,
            "info": python_info,
        }
        
        # 检查依赖包
        results["packages"] = EnvChecker.check_all_packages()
        
        # 检查数据库连接
        db_ok, db_info = EnvChecker.check_database_connection()
        results["database"] = {
            "ok": db_ok,
            "info": db_info,
        }
        
        # 检查配置文件
        config_ok, config_info = EnvChecker.check_config_file()
        results["config"] = {
            "ok": config_ok,
            "info": config_info,
        }
        
        # 计算总体状态
        # 必需：Python版本、必需包、数据库连接
        required_packages_ok = all(
            p["installed"] for p in results["packages"]["required"].values()
        )
        
        results["overall"] = (
            python_ok and 
            required_packages_ok and 
            db_ok
        )
        
        logger.info(f"环境检查完成，总体状态: {'通过' if results['overall'] else '未通过'}")
        
        return results
    
    @staticmethod
    def print_report(results: Dict) -> None:
        """打印检查报告
        
        Args:
            results: 检查结果字典
        """
        print("\n" + "=" * 60)
        print("环境检查报告")
        print("=" * 60)
        
        # Python版本
        python_status = "✓" if results["python"]["ok"] else "✗"
        print(f"\n{python_status} Python版本: {results['python']['info']}")
        
        # 依赖包
        print("\n依赖包检查:")
        print("  必需包:")
        for name, info in results["packages"]["required"].items():
            status = "✓" if info["installed"] else "✗"
            version = f" ({info['version']})" if info["version"] else ""
            print(f"    {status} {name}{version}")
        
        print("  可选包:")
        for name, info in results["packages"]["optional"].items():
            status = "✓" if info["installed"] else "○"
            version = f" ({info['version']})" if info["version"] else ""
            print(f"    {status} {name}{version}")
        
        # 数据库
        db_status = "✓" if results["database"]["ok"] else "✗"
        print(f"\n{db_status} 数据库: {results['database']['info']}")
        
        # 配置文件
        config_status = "✓" if results["config"]["ok"] else "○"
        print(f"{config_status} 配置文件: {results['config']['info']}")
        
        # 总体状态
        print("\n" + "=" * 60)
        if results["overall"]:
            print("✓ 环境检查通过，可以开始初始化")
        else:
            print("✗ 环境检查未通过，请修复上述问题")
        print("=" * 60 + "\n")


# 命令行接口
if __name__ == "__main__":
    results = EnvChecker.check_all()
    EnvChecker.print_report(results)
    
    # 返回退出码
    sys.exit(0 if results["overall"] else 1)
