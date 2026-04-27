"""自定义指标执行引擎

在服务端安全执行用户编写的Python指标代码，提供沙箱环境、
超时控制、NaN清理和结果验证等能力。
"""

import re
import math
import time
import asyncio
import traceback
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np
import pandas as pd

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 默认执行超时（秒）
DEFAULT_EXEC_TIMEOUT = 10.0

# 最大允许K线数据条数
MAX_KLINE_LIMIT = 2000


class IndicatorExecutionError(Exception):
    """指标执行错误基类"""
    def __init__(self, message: str, error_type: str = "runtime", detail: str = ""):
        self.message = message
        self.error_type = error_type  # syntax / runtime / timeout / security
        self.detail = detail
        super().__init__(message)


def _generate_mock_df(num_bars: int = 100) -> pd.DataFrame:
    """生成模拟K线数据用于代码验证
    
    Args:
        num_bars: K线条数
        
    Returns:
        模拟DataFrame，包含time/open/high/low/close/volume列
    """
    np.random.seed(42)
    
    base_price = 50000.0
    returns = np.random.randn(num_bars) * 0.02
    prices = base_price * np.cumprod(1 + returns)
    
    opens = prices * (1 + np.random.rand(num_bars) * 0.005)
    highs = np.maximum(opens, prices) * (1 + np.abs(np.random.randn(num_bars)) * 0.01)
    lows = np.minimum(opens, prices) * (1 - np.abs(np.random.randn(num_bars)) * 0.01)
    closes = prices
    volumes = np.random.randint(100, 10000, size=num_bars).astype(float)
    
    timestamps = pd.date_range("2024-01-01", periods=num_bars, freq="h")
    
    return pd.DataFrame({
        "time": timestamps.astype(int) // 10**9,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def _build_kline_dataframe(kline_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """将前端传入的K线数据转换为DataFrame
    
    Args:
        kline_data: K线数据列表 [{timestamp, open, high, low, close, volume}, ...]
        
    Returns:
        pandas DataFrame
    """
    if not kline_data:
        return _generate_mock_df()
    
    df = pd.DataFrame(kline_data)
    
    timestamp_col = None
    for col in ["timestamp", "time"]:
        if col in df.columns:
            timestamp_col = col
            break
    
    if timestamp_col and timestamp_col != "time":
        df["time"] = df[timestamp_col]
    
    for required_col in ["open", "high", "low", "close", "volume"]:
        if required_col not in df.columns:
            df[required_col] = 0.0
    
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    if "time" in df.columns:
        ts = df["time"]
        if ts.dtype == "object" or not (ts > 1e12).any():
            try:
                df["time"] = pd.to_datetime(ts).astype(int) // 10**9
            except Exception:
                pass
    
    return df


def clean_nan(obj):
    """
    递归清理NaN/Inf值，确保JSON序列化安全
    """
    if obj is None:
        return None
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_nan(item) for item in obj]
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return clean_nan(obj.tolist())
    if isinstance(obj, pd.Series):
        return clean_nan(obj.tolist())
    return obj


def _validate_output(output: Any) -> Tuple[bool, str]:
    """验证output变量格式是否符合规范
    
    Returns:
        (is_valid, error_message)
    """
    if output is None:
        return False, "output变量为None"
    if not isinstance(output, dict):
        return False, f"output必须是dict类型，当前为{type(output).__name__}"
    
    if "plots" not in output:
        return False, "output中缺少'plots'字段"
    if not isinstance(output["plots"], list):
        return False, "'plots'必须是list类型"
    
    for i, plot in enumerate(output["plots"]):
        if not isinstance(plot, dict):
            return False, f"plots[{i}]必须是dict类型"
        if "data" not in plot:
            return False, f"plots[{i}]中缺少'data'字段"
        if not isinstance(plot["data"], list):
            return False, f"plots[{i}].data必须是list类型"
    
    signals = output.get("signals")
    if signals is not None:
        if not isinstance(signals, list):
            return False, "'signals'必须是list类型或不存在"
        for i, signal in enumerate(signals):
            if not isinstance(signal, dict):
                return False, f"signals[{i}]必须是dict类型"
            if signal.get("type") not in ("buy", "sell"):
                return False, f"signals[{i}].type必须是'buy'或'sell'"
            if "data" not in signal:
                return False, f"signals[{i}]中缺少'data'字段"
    
    return True, ""


class IndicatorExecutor:
    """自定义指标执行引擎
    
    负责在安全的沙箱环境中执行用户Python指标代码，
    提供超时控制、缓存、NaN清理等功能。
    """
    
    def __init__(self, timeout: float = DEFAULT_EXEC_TIMEOUT):
        self.timeout = timeout
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._cache_max_size = 100
        self._cache_ttl = 60.0
    
    def _cache_key(self, indicator_id: int, symbol: str, period: str,
                   params_hash: str, data_hash: str) -> str:
        return f"{indicator_id}:{symbol}:{period}:{params_hash}:{data_hash}"
    
    def _cache_get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        result, ts = self._cache[key]
        if time.time() - ts > self._cache_ttl:
            del self._cache[key]
            return None
        return result
    
    def _cache_set(self, key: str, value: Any):
        if len(self._cache) >= self._cache_max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (value, time.time())
    
    @staticmethod
    def _build_param_getter(params: Dict[str, Any]):
        """构建参数获取函数注入到用户代码执行环境"""
        
        def _get_param(key: str, default=None):
            if params and key in params:
                val = params[key]
                if isinstance(val, str):
                    if val.isdigit():
                        return int(val)
                    try:
                        return float(val)
                    except ValueError:
                        return val
                return val
            return default
        
        return _get_param
    
    async def verify_code(self, code: str) -> Dict[str, Any]:
        """验证指标代码语法和输出格式
        
        使用mock数据执行用户代码，检查是否能正确产出output
        
        Args:
            code: 用户Python代码
            
        Returns:
            验证结果 { valid, message, plots_count, signals_count }
        """
        # 语法检查
        try:
            compile(code, '<indicator>', 'exec')
        except SyntaxError as e:
            line_num = e.lineno or 0
            offset = e.offset or 0
            lines = code.split('\n')
            error_line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            pointer = " " * (offset - 1) + "^" if offset > 0 else ""
            return {
                "valid": False,
                "message": f"第{line_num}行语法错误: {e.msg}\n{error_line}\n{pointer}",
                "plots_count": 0,
                "signals_count": 0,
            }
        
        # 用mock数据执行
        mock_df = _generate_mock_df(80)
        result = await self.execute(
            code=code,
            kline_data=[],
            params={},
            use_mock=True,
            mock_df=mock_df,
        )
        
        if result["success"]:
            return {
                "valid": True,
                "message": "代码验证通过",
                "plots_count": result.get("plots_count", 0),
                "signals_count": result.get("signals_count", 0),
            }
        else:
            return {
                "valid": False,
                "message": result.get("error", "未知错误"),
                "plots_count": 0,
                "signals_count": 0,
            }
    
    async def execute(
        self,
        code: str,
        kline_data: List[Dict[str, Any]],
        params: Dict[str, Any] = None,
        *,
        use_mock: bool = False,
        mock_df: pd.DataFrame = None,
    ) -> Dict[str, Any]:
        """执行用户Python指标代码
        
        Args:
            code: 用户Python代码
            kline_data: K线数据列表
            params: 用户配置的参数字典
            use_mock: 是否使用mock数据
            mock_df: 预生成的mock DataFrame
            
        Returns:
            执行结果字典:
            {
                "success": bool,
                "name": str,
                "plots": [...],
                "signals": [...],
                "plots_count": int,
                "signals_count": int,
                "error": str (失败时有值),
                "calculatedVars": {}
            }
        """
        start_time = time.time()
        
        # 构建DataFrame
        if use_mock and mock_df is not None:
            df = mock_df.copy()
        elif kline_data:
            limited_data = kline_data[:MAX_KLINE_LIMIT]
            df = _build_kline_dataframe(limited_data)
        else:
            df = _generate_mock_df(100)
        
        # 构建安全执行环境
        exec_env = self._create_safe_exec_env(df, params)
        
        # 带超时的同步执行
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._exec_sync(code, exec_env)),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.warning(f"指标执行超时: {elapsed:.2f}s > {self.timeout}s")
            return {
                "success": False,
                "error": f"指标执行超时({self.timeout:.0f}s)，请简化计算逻辑或减少数据量",
                "name": "",
                "plots": [],
                "signals": [],
                "plots_count": 0,
                "signals_count": 0,
                "calculatedVars": {},
            }
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"指标执行异常: {e}\n{traceback.format_exc()}")
            
            error_msg = str(e)
            tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
            user_tb = [l for l in tb_lines if "<string>" in l or "<indicator>" in l]
            if user_tb:
                error_msg += "\n" + "".join(user_tb[-3:])
            
            return {
                "success": False,
                "error": f"运行时错误: {error_msg}",
                "name": "",
                "plots": [],
                "signals": [],
                "plots_count": 0,
                "signals_count": 0,
                "calculatedVars": {},
            }
        
        elapsed = time.time() - start_time
        logger.debug(f"指标执行完成: {elapsed:.3f}s, 数据量={len(df)}")
        
        return result
    
    def _create_safe_exec_env(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """构建受限的安全执行环境"""
        safe_builtins = {
            "abs": abs, "all": all, "any": any, "bool": bool,
            "dict": dict, "enumerate": enumerate, "filter": filter,
            "float": float, "format": format, "frozenset": frozenset,
            "getattr": getattr, "hasattr": hasattr, "hash": hash,
            "int": int, "isinstance": isinstance, "iter": iter,
            "len": len, "list": list, "map": map, "max": max,
            "min": min, "next": next, "object": object, "pow": pow,
            "print": print, "property": property, "range": range,
            "repr": repr, "reversed": reversed, "round": round,
            "set": set, "slice": slice, "sorted": sorted, "str": str,
            "sum": sum, "tuple": tuple, "type": type, "zip": zip,
            "True": True, "False": False, "None": None,
            "Exception": Exception, "ValueError": ValueError,
            "TypeError": TypeError, "KeyError": KeyError,
            "IndexError": IndexError, "AttributeError": AttributeError,
            "RuntimeError": RuntimeError, "StopIteration": StopIteration,
        }
        
        return {
            "__builtins__": safe_builtins,
            "df": df,
            "pd": pd,
            "np": np,
            "math": math,
            "_get_param": self._build_param_getter(params),
            "output": None,
        }
    
    def _exec_sync(self, code: str, exec_env: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行用户代码（在线程池中调用）"""
        try:
            exec(code, exec_env)
        except SyntaxError as e:
            raise IndicatorExecutionError(
                f"语法错误(第{e.lineno}行): {e.msg}",
                error_type="syntax",
                detail=f"{e.text}",
            )
        except ImportError as e:
            raise IndicatorExecutionError(
                f"禁止导入模块: {e.name}",
                error_type="security",
                detail="不允许导入外部模块，请直接使用已提供的pd和np",
            )
        except RecursionError:
            raise IndicatorExecutionError(
                "检测到无限递归",
                error_type="runtime",
                detail="请检查代码逻辑避免循环调用",
            )
        except MemoryError:
            raise IndicatorExecutionError(
                "内存不足",
                error_type="runtime",
                detail="请减少中间变量的内存占用",
            )
        except ZeroDivisionError as e:
            raise IndicatorExecutionError(
                f"除零错误: {e}",
                error_type="runtime",
                detail="请添加除零保护（如 .replace(0, np.nan)）",
            )
        except Exception as e:
            raise e
        
        output = exec_env.get("output")
        
        # 验证output格式
        is_valid, validation_error = _validate_output(output)
        if not is_valid:
            raise IndicatorExecutionError(
                f"输出格式无效: {validation_error}",
                error_type="runtime",
                detail="output必须为包含plots列表的字典",
            )
        
        indicator_name = exec_env.get("my_indicator_name", "自定义指标")
        
        # 清理NaN并提取数据
        cleaned_output = clean_nan(output)
        
        plots = []
        for plot in cleaned_output.get("plots", []):
            data = plot.get("data", [])
            plots.append({
                "name": plot.get("name", ""),
                "data": data,
                "color": plot.get("color", "#1890ff"),
                "overlay": plot.get("overlay", True),
                "type": plot.get("type", "line"),
            })
        
        signals = []
        for sig in cleaned_output.get("signals", []):
            signals.append({
                "type": sig.get("type", "buy"),
                "text": sig.get("text", ""),
                "data": sig.get("data", []),
                "color": sig.get("color", "#1890ff"),
            })
        
        return {
            "success": True,
            "name": indicator_name,
            "plots": plots,
            "signals": signals,
            "plots_count": len(plots),
            "signals_count": len(signals),
            "error": None,
            "calculatedVars": clean_nan(cleaned_output.get("calculatedVars", {})),
        }


def parse_indicator_params(code: str) -> List[Dict[str, Any]]:
    """从指标代码中解析参数声明
    
    支持 _get_param("key", default) 和显式赋值两种模式
    
    Args:
        code: 指标源码
        
    Returns:
        参数列表 [{key, default, type, description}]
    """
    params = []
    seen_keys = set()
    
    pattern = r'_get_param\(\s*["\'](\w+)["\']\s*,\s*([^)]*)\s*\)'
    for match in re.finditer(pattern, code):
        key = match.group(1)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        
        raw_default = match.group(2).strip()
        param_info = {"key": key, "default": raw_default}
        
        try:
            if raw_default.isdigit():
                param_info["type"] = "int"
                param_info["default_value"] = int(raw_default)
            else:
                float(raw_default)
                param_info["type"] = "float"
                param_info["default_value"] = float(raw_default)
        except ValueError:
            if raw_default.lower() in ("true", "false"):
                param_info["type"] = "bool"
                param_info["default_value"] = raw_default.lower() == "true"
            else:
                param_info["type"] = "string"
                param_info["default_value"] = raw_default
        
        params.append(param_info)
    
    assignment_pattern = r'^(\w[\w]*)\s*=\s*(\d+\.?\d*|["\'][^"\']*["\'])'
    for match in re.finditer(assignment_pattern, code, re.MULTILINE):
        var_name = match.group(1)
        if var_name in seen_keys or var_name.startswith("_") or var_name in (
            "df", "pd", "np", "output", "my_indicator_name", "my_indicator_description",
        ):
            continue
        
        raw_val = match.group(2).strip()
        try:
            if raw_val.isdigit():
                val_type = "int"
                val = int(raw_val)
            else:
                float(raw_val)
                val_type = "float"
                val = float(raw_val)
        except ValueError:
            continue
        
        params.append({
            "key": var_name,
            "default": raw_val,
            "type": val_type,
            "default_value": val,
        })
        seen_keys.add(var_name)
    
    return params
