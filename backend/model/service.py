# 模型训练服务
# 实现模型训练、评估、保存和加载等功能

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
import pickle
import json

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent  # /Users/liupeng/workspace/qbot
sys.path.append(str(project_root))

# 导入QLib相关模块
from qlib.data import D
from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.dataset import DatasetH
from qlib.model.trainer import TrainerR
from qlib.model.base import Model
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord
from qlib.utils import init_instance_by_config


class ModelService:
    """
    模型训练服务类，用于训练、评估和管理量化交易模型
    """

    def __init__(self):
        """初始化模型训练服务"""
        self.models = {
            "lightgbm": "qlib.contrib.model.gbdt.LGBModel",
            "xgboost": "qlib.contrib.model.gbdt.XGBModel",
            "random_forest": "qlib.contrib.model.sklearn.RFModel",
            "linear": "qlib.contrib.model.sklearn.LinearModel",
            "dnn": "qlib.contrib.model.pytorch.DNNModel",
            "lstm": "qlib.contrib.model.pytorch.LSTMModel",
            "transformer": "qlib.contrib.model.pytorch.TransformerModel"
        }

        # 模型保存路径
        self.model_save_dir = Path(project_root) / "backend" / "model" / "saved_models"
        self.model_save_dir.mkdir(parents=True, exist_ok=True)

    def get_model_list(self):
        """
        获取所有支持的模型类型列表

        :return: 模型类型列表
        """
        return list(self.models.keys())

    def train_model(self, model_config, dataset_config, trainer_config):
        """
        训练模型

        :param model_config: 模型配置
        :param dataset_config: 数据集配置
        :param trainer_config: 训练器配置
        :return: 训练结果
        """
        try:
            logger.info(f"开始训练模型，模型类型: {model_config.get('class')}")

            # 初始化数据集
            dataset = init_instance_by_config(dataset_config)

            # 初始化模型
            model = init_instance_by_config(model_config)

            # 初始化训练器
            trainer = init_instance_by_config(trainer_config)

            # 开始训练
            trainer.fit(model, dataset)

            # 保存模型
            model_name = model_config.get("model_name", "default_model")
            self.save_model(model, model_name)

            logger.info(f"模型训练完成，模型名称: {model_name}")

            return {
                "model_name": model_name,
                "status": "success",
                "message": "模型训练完成"
            }
        except Exception as e:
            logger.error(f"模型训练失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }

    def evaluate_model(self, model_name, dataset_config):
        """
        评估模型

        :param model_name: 模型名称
        :param dataset_config: 数据集配置
        :return: 评估结果
        """
        try:
            logger.info(f"开始评估模型，模型名称: {model_name}")

            # 加载模型
            model = self.load_model(model_name)

            # 初始化数据集
            dataset = init_instance_by_config(dataset_config)

            # 获取测试集
            test_dataset = dataset.prepare("test", col_set=["feature", "label"])

            # 模型预测
            preds = model.predict(test_dataset)

            # 获取真实标签
            labels = test_dataset["label"]

            # 计算评估指标
            from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

            mse = mean_squared_error(labels, preds)
            mae = mean_absolute_error(labels, preds)
            r2 = r2_score(labels, preds)

            # 计算IC和IR
            ic = preds.corr(labels, method="spearman")

            logger.info(f"模型评估完成，模型名称: {model_name}")

            return {
                "model_name": model_name,
                "status": "success",
                "metrics": {
                    "mse": mse,
                    "mae": mae,
                    "r2": r2,
                    "ic": ic
                }
            }
        except Exception as e:
            logger.error(f"模型评估失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }

    def predict(self, model_name, data):
        """
        使用模型进行预测

        :param model_name: 模型名称
        :param data: 预测数据
        :return: 预测结果
        """
        try:
            logger.info(f"开始使用模型预测，模型名称: {model_name}")

            # 加载模型
            model = self.load_model(model_name)

            # 进行预测
            preds = model.predict(data)

            logger.info(f"模型预测完成，模型名称: {model_name}")

            return {
                "model_name": model_name,
                "status": "success",
                "predictions": preds.tolist() if isinstance(preds, np.ndarray) else preds
            }
        except Exception as e:
            logger.error(f"模型预测失败: {e}")
            logger.exception(e)
            return {
                "status": "failed",
                "message": str(e)
            }

    def save_model(self, model, model_name):
        """
        保存模型

        :param model: 模型对象
        :param model_name: 模型名称
        :return: 是否保存成功
        """
        try:
            # 保存模型文件
            model_path = self.model_save_dir / f"{model_name}.pkl"
            with open(model_path, "wb") as f:
                pickle.dump(model, f)

            logger.info(f"模型保存成功，模型路径: {model_path}")
            return True
        except Exception as e:
            logger.error(f"模型保存失败: {e}")
            logger.exception(e)
            return False

    def load_model(self, model_name):
        """
        加载模型

        :param model_name: 模型名称
        :return: 模型对象
        """
        try:
            # 加载模型文件
            model_path = self.model_save_dir / f"{model_name}.pkl"
            with open(model_path, "rb") as f:
                model = pickle.load(f)

            logger.info(f"模型加载成功，模型路径: {model_path}")
            return model
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            logger.exception(e)
            return None

    def delete_model(self, model_name):
        """
        删除模型

        :param model_name: 模型名称
        :return: 是否删除成功
        """
        try:
            # 删除模型文件
            model_path = self.model_save_dir / f"{model_name}.pkl"
            if model_path.exists():
                model_path.unlink()
                logger.info(f"模型删除成功，模型路径: {model_path}")
                return True
            else:
                logger.warning(f"模型文件不存在，模型名称: {model_name}")
                return False
        except Exception as e:
            logger.error(f"模型删除失败: {e}")
            logger.exception(e)
            return False

    def list_saved_models(self):
        """
        列出所有保存的模型

        :return: 保存的模型列表
        """
        try:
            # 获取所有模型文件
            model_files = list(self.model_save_dir.glob("*.pkl"))
            model_list = [file.stem for file in model_files]

            logger.info(f"获取保存的模型列表成功，模型数量: {len(model_list)}")
            return model_list
        except Exception as e:
            logger.error(f"获取保存的模型列表失败: {e}")
            logger.exception(e)
            return []

    def get_model_config(self, model_name):
        """
        获取模型配置

        :param model_name: 模型名称
        :return: 模型配置
        """
        try:
            # 加载模型配置文件
            config_path = self.model_save_dir / f"{model_name}_config.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = json.load(f)
                return config
            else:
                logger.warning(f"模型配置文件不存在，模型名称: {model_name}")
                return None
        except Exception as e:
            logger.error(f"获取模型配置失败: {e}")
            logger.exception(e)
            return None

    def save_model_config(self, model_name, config):
        """
        保存模型配置

        :param model_name: 模型名称
        :param config: 模型配置
        :return: 是否保存成功
        """
        try:
            # 保存模型配置文件
            config_path = self.model_save_dir / f"{model_name}_config.json"
            with open(config_path, "w") as f:
                json.dump(config, f, indent=4)

            logger.info(f"模型配置保存成功，配置路径: {config_path}")
            return True
        except Exception as e:
            logger.error(f"模型配置保存失败: {e}")
            logger.exception(e)
            return False

    def create_model_config(self, model_type, params):
        """
        创建模型配置

        :param model_type: 模型类型
        :param params: 模型参数
        :return: 模型配置
        """
        try:
            # 获取模型类路径
            model_class = self.models.get(model_type)
            if not model_class:
                logger.error(f"不支持的模型类型: {model_type}")
                return None

            # 创建模型配置
            model_config = {
                "class": model_class,
                "module_path": None,
                "kwargs": params
            }

            logger.info(f"模型配置创建成功，模型类型: {model_type}")
            return model_config
        except Exception as e:
            logger.error(f"模型配置创建失败: {e}")
            logger.exception(e)
            return None
