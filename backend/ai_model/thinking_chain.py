"""思维链管理模块

提供思维链配置的 CRUD 操作和 TOML 配置文件导入功能
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import toml
from sqlalchemy import and_, desc, func, create_engine
from sqlalchemy.orm import Session, sessionmaker

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

try:
    from ai_model.thinking_chain_models import ThinkingChain, Base
except ImportError:
    # 用于直接运行测试时
    from thinking_chain_models import ThinkingChain, Base


# 数据库配置
_engine = None
_SessionLocal = None


def _get_engine():
    """获取数据库引擎（延迟初始化）"""
    global _engine
    if _engine is None:
        import os
        db_type = os.environ.get("DB_TYPE", "sqlite")
        default_db_path = os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(default_db_path, exist_ok=True)

        if db_type == "sqlite":
            db_file = os.environ.get("DB_FILE", os.path.join(default_db_path, "quantcell.db"))
            _engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
        else:
            db_file = os.environ.get("DB_FILE", os.path.join(default_db_path, "quantcell.db"))
            _engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})

        # 绑定 Base metadata
        Base.metadata.bind = _engine

    return _engine


def _get_session_local():
    """获取会话工厂（延迟初始化）"""
    global _SessionLocal
    if _SessionLocal is None:
        engine = _get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


class ThinkingChainManager:
    """思维链管理器

    用于操作 thinking_chains 表，提供 CRUD 操作方法
    支持思维链配置的创建、查询、更新、删除和 TOML 导入
    """

    @staticmethod
    def _get_db() -> Session:
        """获取数据库会话"""
        SessionLocal = _get_session_local()
        return SessionLocal()

    @staticmethod
    def create_thinking_chain(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建思维链配置

        Args:
            data: 思维链数据，包含以下字段:
                - chain_type: 思维链类型 (strategy_generation/indicator_generation)
                - name: 思维链名称
                - description: 思维链描述（可选）
                - steps: 思维链步骤列表
                - is_active: 是否激活（可选，默认True）

        Returns:
            Optional[Dict]: 创建成功的记录信息，失败返回 None
        """
        db = ThinkingChainManager._get_db()
        try:
            # 验证必需字段
            if "chain_type" not in data or not data["chain_type"]:
                logger.error("创建思维链失败: chain_type 是必需字段")
                return None
            if "name" not in data or not data["name"]:
                logger.error("创建思维链失败: name 是必需字段")
                return None
            if "steps" not in data or not data["steps"]:
                logger.error("创建思维链失败: steps 是必需字段")
                return None

            chain = ThinkingChain(
                id=str(uuid.uuid4()),
                chain_type=data["chain_type"],
                name=data["name"],
                description=data.get("description"),
                steps=json.dumps(data["steps"], ensure_ascii=False),
                is_active=data.get("is_active", True),
            )
            db.add(chain)
            db.commit()
            db.refresh(chain)

            logger.info(f"思维链创建成功: id={chain.id}, name={chain.name}, type={chain.chain_type}")
            return chain.to_dict()
        except Exception as e:
            db.rollback()
            logger.error(f"创建思维链失败: error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_thinking_chain(chain_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取单个思维链配置

        Args:
            chain_id: 思维链 ID

        Returns:
            Optional[Dict]: 思维链信息，不存在返回 None
        """
        db = ThinkingChainManager._get_db()
        try:
            chain = db.query(ThinkingChain).filter(ThinkingChain.id == chain_id).first()
            if chain:
                return chain.to_dict()
            return None
        except Exception as e:
            logger.error(f"获取思维链失败: id={chain_id}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_thinking_chains(
        chain_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 10,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """获取思维链配置列表，支持筛选

        Args:
            chain_type: 按类型筛选（可选）
            is_active: 按激活状态筛选（可选）
            page: 页码，从 1 开始
            page_size: 每页记录数
            sort_by: 排序字段
            sort_order: 排序顺序，asc 或 desc

        Returns:
            Dict: 包含记录列表和分页信息
        """
        db = ThinkingChainManager._get_db()
        try:
            query = db.query(ThinkingChain)

            # 应用筛选条件
            if chain_type is not None:
                query = query.filter(ThinkingChain.chain_type == chain_type)
            if is_active is not None:
                query = query.filter(ThinkingChain.is_active == is_active)

            # 计算总记录数
            total = query.count()

            # 验证排序字段
            allowed_sort_fields = ["created_at", "updated_at", "name", "chain_type"]
            if sort_by not in allowed_sort_fields:
                sort_by = "created_at"

            # 应用排序
            sort_column = getattr(ThinkingChain, sort_by)
            if sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)

            # 应用分页
            offset = (page - 1) * page_size
            chains = query.offset(offset).limit(page_size).all()

            # 计算总页数
            pages = (total + page_size - 1) // page_size if page_size > 0 else 0

            return {
                "items": [chain.to_dict() for chain in chains],
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
            }
        except Exception as e:
            logger.error(f"查询思维链列表失败: error={e}")
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "pages": 0,
            }
        finally:
            db.close()

    @staticmethod
    def update_thinking_chain(chain_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新思维链配置

        Args:
            chain_id: 思维链 ID
            data: 要更新的字段，可包含:
                - chain_type: 思维链类型
                - name: 思维链名称
                - description: 思维链描述
                - steps: 思维链步骤列表
                - is_active: 是否激活

        Returns:
            Optional[Dict]: 更新后的记录信息，失败返回 None
        """
        db = ThinkingChainManager._get_db()
        try:
            chain = db.query(ThinkingChain).filter(ThinkingChain.id == chain_id).first()
            if not chain:
                logger.warning(f"思维链不存在: id={chain_id}")
                return None

            # 更新字段
            if "chain_type" in data:
                chain.chain_type = data["chain_type"]
            if "name" in data:
                chain.name = data["name"]
            if "description" in data:
                chain.description = data["description"]
            if "steps" in data:
                chain.steps = json.dumps(data["steps"], ensure_ascii=False)
            if "is_active" in data:
                chain.is_active = data["is_active"]

            db.commit()
            db.refresh(chain)

            logger.info(f"思维链更新成功: id={chain_id}")
            return chain.to_dict()
        except Exception as e:
            db.rollback()
            logger.error(f"更新思维链失败: id={chain_id}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def delete_thinking_chain(chain_id: str) -> bool:
        """删除思维链配置

        Args:
            chain_id: 思维链 ID

        Returns:
            bool: 删除成功返回 True，失败返回 False
        """
        db = ThinkingChainManager._get_db()
        try:
            chain = db.query(ThinkingChain).filter(ThinkingChain.id == chain_id).first()
            if chain:
                db.delete(chain)
                db.commit()
                logger.info(f"思维链删除成功: id={chain_id}")
                return True
            logger.warning(f"思维链不存在: id={chain_id}")
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"删除思维链失败: id={chain_id}, error={e}")
            return False
        finally:
            db.close()

    @staticmethod
    def import_from_toml(file_content: str, update_existing: bool = True) -> Dict[str, Any]:
        """从 TOML 文件内容导入思维链配置

        Args:
            file_content: TOML 文件内容字符串
            update_existing: 是否更新已存在的配置（按名称和类型匹配）

        Returns:
            Dict: 导入结果，包含:
                - success: 是否成功
                - created: 新创建的记录数
                - updated: 更新的记录数
                - failed: 失败的记录数
                - errors: 错误信息列表
                - items: 导入的记录列表
        """
        result = {
            "success": True,
            "created": 0,
            "updated": 0,
            "failed": 0,
            "errors": [],
            "items": [],
        }

        try:
            # 解析 TOML 内容
            config = toml.loads(file_content)
        except toml.TomlDecodeError as e:
            result["success"] = False
            result["errors"].append(f"TOML 解析错误: {e}")
            return result

        db = ThinkingChainManager._get_db()
        try:
            # 获取思维链列表
            chains = config.get("thinking_chain", [])
            if not isinstance(chains, list):
                chains = [chains]

            for chain_data in chains:
                try:
                    # 验证必需字段
                    if "chain_type" not in chain_data:
                        raise ValueError("缺少必需字段: chain_type")
                    if "name" not in chain_data:
                        raise ValueError("缺少必需字段: name")
                    if "steps" not in chain_data:
                        raise ValueError("缺少必需字段: steps")

                    chain_type = chain_data["chain_type"]
                    name = chain_data["name"]
                    steps = chain_data["steps"]
                    description = chain_data.get("description")
                    is_active = chain_data.get("is_active", True)

                    # 检查是否已存在
                    existing = None
                    if update_existing:
                        existing = (
                            db.query(ThinkingChain)
                            .filter(
                                and_(
                                    ThinkingChain.chain_type == chain_type,
                                    ThinkingChain.name == name,
                                )
                            )
                            .first()
                        )

                    if existing:
                        # 更新现有配置
                        existing.description = description
                        existing.steps = json.dumps(steps, ensure_ascii=False)
                        existing.is_active = is_active
                        db.commit()
                        db.refresh(existing)
                        result["updated"] += 1
                        result["items"].append({
                            "id": existing.id,
                            "name": existing.name,
                            "chain_type": existing.chain_type,
                            "action": "updated",
                        })
                        logger.info(f"思维链配置更新: id={existing.id}, name={name}")
                    else:
                        # 创建新配置
                        new_chain = ThinkingChain(
                            id=str(uuid.uuid4()),
                            chain_type=chain_type,
                            name=name,
                            description=description,
                            steps=json.dumps(steps, ensure_ascii=False),
                            is_active=is_active,
                        )
                        db.add(new_chain)
                        db.commit()
                        db.refresh(new_chain)
                        result["created"] += 1
                        result["items"].append({
                            "id": new_chain.id,
                            "name": new_chain.name,
                            "chain_type": new_chain.chain_type,
                            "action": "created",
                        })
                        logger.info(f"思维链配置创建: id={new_chain.id}, name={name}")

                except Exception as e:
                    result["failed"] += 1
                    error_msg = f"导入思维链 '{chain_data.get('name', 'unknown')}' 失败: {e}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg)

            if result["failed"] > 0 and result["created"] == 0 and result["updated"] == 0:
                result["success"] = False

        except Exception as e:
            result["success"] = False
            result["errors"].append(f"导入过程出错: {e}")
            logger.error(f"TOML 导入失败: error={e}")
        finally:
            db.close()

        return result

    @staticmethod
    def export_to_toml(chain_id: Optional[str] = None) -> str:
        """导出思维链配置为 TOML 格式

        Args:
            chain_id: 特定思维链 ID，如果为 None 则导出所有

        Returns:
            str: TOML 格式字符串
        """
        db = ThinkingChainManager._get_db()
        try:
            if chain_id:
                chain = db.query(ThinkingChain).filter(ThinkingChain.id == chain_id).first()
                chains = [chain] if chain else []
            else:
                chains = db.query(ThinkingChain).all()

            config = {"thinking_chain": []}
            for chain in chains:
                chain_data = {
                    "chain_type": chain.chain_type,
                    "name": chain.name,
                    "description": chain.description,
                    "steps": chain.get_steps(),
                    "is_active": chain.is_active,
                }
                config["thinking_chain"].append(chain_data)

            return toml.dumps(config)
        except Exception as e:
            logger.error(f"导出思维链失败: error={e}")
            return ""
        finally:
            db.close()

    @staticmethod
    def get_active_chain_by_type(chain_type: str) -> Optional[Dict[str, Any]]:
        """获取指定类型的激活思维链

        Args:
            chain_type: 思维链类型

        Returns:
            Optional[Dict]: 思维链信息，不存在返回 None
        """
        db = ThinkingChainManager._get_db()
        try:
            chain = (
                db.query(ThinkingChain)
                .filter(
                    and_(
                        ThinkingChain.chain_type == chain_type,
                        ThinkingChain.is_active == True,
                    )
                )
                .order_by(desc(ThinkingChain.created_at))
                .first()
            )
            if chain:
                return chain.to_dict()
            return None
        except Exception as e:
            logger.error(f"获取激活思维链失败: type={chain_type}, error={e}")
            return None
        finally:
            db.close()
