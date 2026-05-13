"""
K线数据质量检查服务（独立模块）

该模块不依赖任何特定的数据源（数据库/Parquet/API），
通过 DataProvider 抽象接口获取数据，可在 CLI 和 FastAPI 中共用。

主要功能：
- 完整性检查（缺失值、缺失列）
- 连续性检查（时间序列缺口检测）
- 有效性检查（负价格、异常涨跌幅、异常成交量、价格跳空）
- 唯一性检查（重复记录检测）
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import pandas as pd
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from .data_provider import DataProvider


class KlineQualityService:
    """K线数据质量检查服务

    通过依赖注入的方式接收 DataProvider 实例，
    实现与具体数据源的解耦。
    """

    def __init__(self, data_provider: DataProvider):
        """
        初始化质量服务

        Args:
            data_provider: 数据提供者实例（如 ParquetDataProvider）
        """
        self.provider = data_provider

    def check_quality(
        self,
        symbol: str,
        interval: str,
        candle_type: str = "spot",
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行完整的K线数据质量检查

        Args:
            symbol: 交易对符号
            interval: 时间周期
            candle_type: 市场类型
            start: 开始时间
            end: 结束时间

        Returns:
            dict: 包含完整质量报告的字典
        """
        logger.info(f"开始检查 {symbol} {interval} 的K线数据质量")

        # 1. 获取数据
        try:
            df = self.provider.get_kline_data(symbol, interval, candle_type, start, end)
        except FileNotFoundError as e:
            logger.error(f"获取数据失败: {e}")
            return {
                'symbol': symbol,
                'interval': interval,
                'candle_type': candle_type,
                'status': 'error',
                'message': str(e),
                'summary': {},
                'details': {}
            }

        if df.empty:
            logger.warning(f"未找到 {symbol} {interval} 的数据")
            return {
                'symbol': symbol,
                'interval': interval,
                'candle_type': candle_type,
                'status': 'empty',
                'message': f'未找到 {symbol} {interval} 的数据',
                'total_records': 0,
                'summary': {},
                'details': {}
            }

        # 2. 执行各项检查
        results = {
            'symbol': symbol,
            'interval': interval,
            'candle_type': candle_type,
            'total_records': len(df),
            'time_range': self._get_time_range(df),
            'summary': {},
            'details': {
                'integrity': self.check_integrity(df),
                'continuity': self.check_continuity(df, interval),
                'validity': self.check_validity(df),
                'uniqueness': self.check_uniqueness(df)
            }
        }

        # 3. 计算总体评分
        results['summary'] = self._calculate_summary(results['details'])

        logger.info(
            f"检查完成 - 得分: {results['summary'].get('score', 0)}, "
            f"等级: {results['summary'].get('grade', '-')}"
        )

        return results

    def check_integrity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据完整性（缺失值、缺失列）

        Args:
            df: K线数据DataFrame

        Returns:
            Dict[str, Any]: 完整性检查结果
        """
        result = {
            "status": "pass",
            "missing_columns": [],
            "missing_values": {},
            "total_records": len(df)
        }

        # 检查必需列是否存在
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            result["status"] = "fail"
            result["missing_columns"] = missing_cols

        # 检查缺失值
        if not df.empty:
            missing_vals = df.isnull().sum()
            missing_vals = missing_vals[missing_vals > 0].to_dict()
            if missing_vals:
                result["status"] = "fail"
                result["missing_values"] = {k: int(v) for k, v in missing_vals.items()}

        return result

    def check_continuity(self, df: pd.DataFrame, interval: str) -> Dict[str, Any]:
        """
        检查数据连续性（时间序列缺口）

        Args:
            df: K线数据DataFrame
            interval: 时间周期（如 1m, 5m, 15m, 1h, 4h, 1d）

        Returns:
            Dict[str, Any]: 连续性检查结果
        """
        result = {
            "status": "pass",
            "expected_records": 0,
            "actual_records": len(df),
            "missing_records": 0,
            "coverage_ratio": 1.0,
            "gaps": []
        }

        if df.empty:
            return result

        # 时间周期映射
        interval_map = {
            '1m': timedelta(minutes=1), '3m': timedelta(minutes=3),
            '5m': timedelta(minutes=5), '15m': timedelta(minutes=15),
            '30m': timedelta(minutes=30), '1h': timedelta(hours=1),
            '2h': timedelta(hours=2), '4h': timedelta(hours=4),
            '6h': timedelta(hours=6), '8h': timedelta(hours=8),
            '12h': timedelta(hours=12), '1d': timedelta(days=1),
            '1w': timedelta(weeks=1)
        }

        if interval not in interval_map:
            logger.warning(f"不支持的时间周期: {interval}")
            return result

        delta = interval_map[interval]
        df_sorted = df.sort_values('timestamp')

        # 转换时间戳并生成期望的时间序列
        timestamps = pd.to_numeric(df_sorted['timestamp'], errors='coerce')

        if timestamps.empty or timestamps.isna().all():
            return result

        # 自动检测时间戳精度并转换
        ts_min = int(timestamps.min())
        ts_max = int(timestamps.max())
        ts_len = len(str(ts_min))

        if ts_len > 16:  # 纳秒级
            dt_min = pd.to_datetime(timestamps.min(), unit='ns')
            dt_max = pd.to_datetime(timestamps.max(), unit='ns')
            time_unit = 'ns'
        elif ts_len > 13:  # 微秒级
            dt_min = pd.to_datetime(timestamps.min(), unit='us')
            dt_max = pd.to_datetime(timestamps.max(), unit='us')
            time_unit = 'us'
        elif ts_len > 10:  # 毫秒级
            dt_min = pd.to_datetime(timestamps.min(), unit='ms')
            dt_max = pd.to_datetime(timestamps.max(), unit='ms')
            time_unit = 'ms'
        else:  # 秒级
            dt_min = pd.to_datetime(timestamps.min(), unit='s')
            dt_max = pd.to_datetime(timestamps.max(), unit='s')
            time_unit = 's'

        expected_index = pd.date_range(start=dt_min, end=dt_max, freq=delta)
        result["expected_records"] = len(expected_index)
        result["coverage_ratio"] = round(len(df) / len(expected_index), 4) if len(expected_index) > 0 else 0

        # 使用相同的时间单位转换实际时间戳，避免精度不匹配
        actual_dates = pd.to_datetime(timestamps, unit=time_unit)
        missing = expected_index.difference(actual_dates)

        if len(missing) > 0:
            result["status"] = "fail"
            result["missing_records"] = len(missing)

            # 分析连续缺口时间段
            gaps = self._analyze_gaps(missing.tolist(), delta)
            result["gaps"] = gaps

        return result

    def check_validity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据有效性（负价格、异常值等）

        Args:
            df: K线数据DataFrame

        Returns:
            Dict[str, Any]: 有效性检查结果
        """
        result = {
            "status": "pass",
            "issues": {
                "negative_prices": 0,
                "negative_volumes": 0,
                "invalid_high_low": 0,
                "abnormal_changes": 0,
                "abnormal_volumes": 0
            },
            "issue_details": []
        }

        if df.empty:
            return result

        issues = []

        # 检查负价格
        neg_price = df[(df['open'] < 0) | (df['high'] < 0) | (df['low'] < 0) | (df['close'] < 0)]
        if not neg_price.empty:
            result["status"] = "fail"
            result["issues"]["negative_prices"] = len(neg_price)
            issues.append({"type": "negative_prices", "count": len(neg_price)})

        # 检查负成交量
        neg_vol = df[df['volume'] < 0]
        if not neg_vol.empty:
            result["status"] = "fail"
            result["issues"]["negative_volumes"] = len(neg_vol)
            issues.append({"type": "negative_volumes", "count": len(neg_vol)})

        # 检查 high < low
        invalid_hl = df[df['high'] < df['low']]
        if not invalid_hl.empty:
            result["status"] = "fail"
            result["issues"]["invalid_high_low"] = len(invalid_hl)
            issues.append({"type": "invalid_high_low", "count": len(invalid_hl)})

        # 检查异常涨跌幅 (>20%)
        if len(df) > 1:
            df_copy = df.copy()
            df_copy['pct_change'] = df_copy['close'].pct_change() * 100
            abnormal = df_copy[abs(df_copy['pct_change']) > 20]
            if not abnormal.empty:
                result["status"] = "fail"
                result["issues"]["abnormal_changes"] = len(abnormal)
                issues.append({
                    "type": "abnormal_changes",
                    "count": len(abnormal),
                    "max_change": round(abs(abnormal['pct_change']).max(), 2)
                })

        result["issue_details"] = issues
        return result

    def check_uniqueness(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查数据唯一性（重复记录）

        Args:
            df: K线数据DataFrame

        Returns:
            Dict[str, Any]: 唯一性检查结果
        """
        result = {
            "status": "pass",
            "duplicate_count": 0,
            "duplicate_timestamps": []
        }

        if df.empty or 'timestamp' not in df.columns:
            return result

        dup_mask = df.duplicated(subset=['timestamp'], keep=False)
        if dup_mask.any():
            result["status"] = "fail"
            result["duplicate_count"] = int(dup_mask.sum())
            result["duplicate_timestamps"] = df[dup_mask]['timestamp'].head(10).tolist()

        return result

    def resolve_duplicates(
        self,
        symbol: str,
        interval: str,
        candle_type: str = "spot",
        strategy: str = "keep_first",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        处理重复记录

        Args:
            symbol: 交易对符号
            interval: 时间周期
            candle_type: 市场类型
            strategy: 处理策略 (keep_first/keep_last/keep_max_volume/keep_min_volume)
            dry_run: 是否仅预览不实际执行

        Returns:
            Dict[str, Any]: 处理结果
        """
        from utils.parquet_utils import save_to_parquet
        import shutil

        # 获取数据
        df = self.provider.get_kline_data(symbol, interval, candle_type)

        if df.empty:
            return {'status': 'warning', 'message': '没有数据'}

        # 检测重复记录
        dup_mask = df.duplicated(subset=['timestamp'], keep=False)
        if not dup_mask.any():
            return {'status': 'success', 'message': '没有发现重复记录', 'processed_count': 0}

        # 根据策略处理重复记录
        original_count = len(df)

        if strategy == "keep_first":
            df_cleaned = df.drop_duplicates(subset=['timestamp'], keep='first')
        elif strategy == "keep_last":
            df_cleaned = df.drop_duplicates(subset=['timestamp'], keep='last')
        elif strategy == "keep_max_volume":
            df_cleaned = df.sort_values('volume', ascending=False).drop_duplicates(subset=['timestamp'], keep='first')
            df_cleaned = df_cleaned.sort_values('timestamp').reset_index(drop=True)
        elif strategy == "keep_min_volume":
            df_cleaned = df.sort_values('volume', ascending=True).drop_duplicates(subset=['timestamp'], keep='first')
            df_cleaned = df_cleaned.sort_values('timestamp').reset_index(drop=True)
        else:
            return {'status': 'error', 'message': f'不支持的处理策略: {strategy}'}

        removed_count = original_count - len(df_cleaned)

        if dry_run:
            return {
                'status': 'preview',
                'original_count': original_count,
                'remaining_count': len(df_cleaned),
                'removed_count': removed_count,
                'strategy': strategy
            }

        # 备份原文件
        from scripts.data_cli import _find_parquet_file
        parquet_path = _find_parquet_file(symbol, interval, candle_type)
        backup_path = parquet_path.with_suffix('.parquet.bak')

        try:
            shutil.copy2(parquet_path, backup_path)

            # 保存清理后的数据
            save_to_parquet(df_cleaned, parquet_path)

            logger.info(f"已处理重复记录: {symbol} {interval}, 策略={strategy}, 删除{removed_count}条")

            return {
                'status': 'success',
                'original_count': original_count,
                'remaining_count': len(df_cleaned),
                'removed_count': removed_count,
                'strategy': strategy,
                'backup_path': str(backup_path)
            }
        except Exception as e:
            logger.error(f"处理重复记录失败: {e}")
            return {'status': 'error', 'message': str(e)}

    def _get_time_range(self, df: pd.DataFrame) -> Dict[str, str]:
        """
        获取数据的时间范围

        Args:
            df: K线数据DataFrame

        Returns:
            Dict[str, str]: {"start": "YYYY-MM-DD HH:MM", "end": "YYYY-MM-DD HH:MM"}
        """
        if df.empty or 'timestamp' not in df.columns:
            return {"start": "-", "end": "-"}

        ts = df['timestamp']
        ts_min = int(ts.min()) if hasattr(ts, 'min') else 0
        ts_max = int(ts.max()) if hasattr(ts, 'max') else 0

        ts_len = len(str(ts_min))
        if ts_len > 16:
            fmt_func = lambda x: datetime.fromtimestamp(x / 1_000_000_000).strftime("%Y-%m-%d %H:%M")
        elif ts_len > 13:
            fmt_func = lambda x: datetime.fromtimestamp(x / 1_000_000).strftime("%Y-%m-%d %H:%M")
        else:
            fmt_func = lambda x: datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M")

        return {"start": fmt_func(ts_min), "end": fmt_func(ts_max)}

    def _analyze_gaps(self, missing_times: list, delta: timedelta) -> list:
        """
        分析连续的缺口时间段

        Args:
            missing_times: 缺失的时间点列表
            delta: 时间间隔

        Returns:
            list: 缺失时间段列表
        """
        if not missing_times:
            return []

        sorted_gaps = sorted(missing_times)
        ranges = []
        start = sorted_gaps[0]
        prev = sorted_gaps[0]

        for t in sorted_gaps[1:]:
            if t - prev > delta * 1.5:  # 允许小幅误差
                ranges.append({
                    "start": str(start),
                    "end": str(prev),
                    "duration": str(prev - start),
                    "missing_count": len([x for x in sorted_gaps if start <= x <= prev])
                })
                start = t
            prev = t

        ranges.append({
            "start": str(start),
            "end": str(sorted_gaps[-1]),
            "duration": str(sorted_gaps[-1] - start),
            "missing_count": len([x for x in sorted_gaps if start <= x <= prev])
        })

        return ranges

    def _calculate_summary(self, details: dict) -> dict:
        """
        计算总体质量评分

        Args:
            details: 各项检查结果的字典

        Returns:
            dict: 包含 score, grade, status 的汇总信息
        """
        scores = []
        weights = {'integrity': 0.25, 'continuity': 0.35, 'validity': 0.25, 'uniqueness': 0.15}

        for check_name, weight in weights.items():
            if check_name in details:
                status = details[check_name].get('status', 'unknown')
                score = 100 if status == 'pass' else (50 if status == 'warning' else 0)
                scores.append(score * weight)

        total_score = sum(scores) if scores else 0

        if total_score >= 90:
            grade = 'A'
            status = 'good'
        elif total_score >= 70:
            grade = 'B'
            status = 'warning'
        else:
            grade = 'C'
            status = 'bad'

        return {
            'score': round(total_score, 1),
            'grade': grade,
            'status': status,
            'checks_passed': sum(1 for d in details.values() if d.get('status') == 'pass'),
            'checks_total': len(details)
        }
