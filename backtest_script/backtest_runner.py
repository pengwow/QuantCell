#!/usr/bin/env python3
"""
独立回测测试脚本
功能：实现与其他系统组件完全解耦的回测流程，支持参数化配置
"""

import argparse
import yaml
import json
import sys
import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd
from backtesting import Backtest
from backtesting.lib import crossover, FractionalBacktest

# 国际化支持
class Translator:
    """简单的翻译器类"""
    def __init__(self, lang="zh-CN"):
        """初始化翻译器
        
        Args:
            lang: 语言代码，默认为中文
        """
        self.lang = lang
        self.translations = {}
        self._load_translations()
    
    def _load_translations(self):
        """加载翻译文件"""
        i18n_dir = Path(__file__).parent.parent / "i18n"
        lang_file = i18n_dir / f"{self.lang}.json"
        
        if lang_file.exists():
            with open(lang_file, "r", encoding="utf-8") as f:
                self.translations = json.load(f)
    
    def get(self, key, default=None):
        """获取翻译
        
        Args:
            key: 翻译键
            default: 默认值
            
        Returns:
            str: 翻译后的文本
        """
        return self.translations.get(key, default or key)

# 创建翻译器实例（默认中文）
translator = Translator()

def parse_args():
    """
    解析命令行参数
    
    Returns:
        argparse.Namespace: 解析后的参数
    """
    parser = argparse.ArgumentParser(description="独立回测测试脚本")
    
    # 配置文件参数
    parser.add_argument("--config", type=str, help="配置文件路径")
    
    # 核心回测参数
    parser.add_argument("--symbol", type=str, help="交易对（如BTCUSDT）")
    parser.add_argument("--start", type=str, help="回测开始时间（YYYY-MM-DD）")
    parser.add_argument("--end", type=str, help="回测结束时间（YYYY-MM-DD）")
    parser.add_argument("--strategy", type=str, help="策略文件路径")
    
    # 输出参数
    parser.add_argument("--output", type=str, help="结果输出路径")
    
    # 数据参数
    parser.add_argument("--data-path", type=str, help="数据文件路径或目录")
    
    # 回测配置参数
    parser.add_argument("--initial-cash", type=float, help="初始资金")
    parser.add_argument("--commission", type=float, help="手续费率")
    
    # 国际化参数
    parser.add_argument("--lang", type=str, default="zh-CN", help="语言代码，默认为中文（zh-CN）")
    
    return parser.parse_args()


def load_config(args):
    """
    加载配置
    
    Args:
        args: 命令行参数
        
    Returns:
        dict: 合并后的配置
    """
    # 从配置文件加载配置
    config = {}
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    
    # 合并命令行参数到配置中（命令行参数优先级更高）
    if args.symbol:
        config["symbol"] = args.symbol
    if args.start:
        config["start_time"] = args.start
    if args.end:
        config["end_time"] = args.end
    if args.strategy:
        config.setdefault("strategy", {})["file"] = args.strategy
    if args.output:
        config.setdefault("output", {})["path"] = args.output
    if args.data_path:
        config.setdefault("data", {})["path"] = args.data_path
    if args.initial_cash is not None:
        config.setdefault("backtest", {})["initial_cash"] = args.initial_cash
    if args.commission is not None:
        config.setdefault("backtest", {})["commission"] = args.commission
    
    # 设置默认值
    config.setdefault("strategy", {}).setdefault("class", "SmaCross")
    config.setdefault("data", {}).setdefault("format", "csv")
    config.setdefault("backtest", {}).setdefault("initial_cash", 10000)
    config.setdefault("backtest", {}).setdefault("commission", 0.001)
    config.setdefault("output", {}).setdefault("format", "console")
    
    return config


def load_data(config):
    """
    加载K线数据
    
    Args:
        config: 配置字典
        
    Returns:
        pd.DataFrame: 加载并格式化后的K线数据
    """
    data_path = config.get("data", {}).get("path")
    data_format = config.get("data", {}).get("format")
    symbol = config.get("symbol", "BTCUSDT")
    
    if not data_path:
        # 如果没有指定数据路径，尝试从默认位置加载
        script_dir = Path(__file__).parent.parent
        default_data_dir = script_dir / "test_data"
        data_path = str(default_data_dir / f"{symbol}.csv")
    
    print(f"加载数据: {data_path}")
    
    if data_format == "csv":
        # 从CSV文件加载数据
        df = pd.read_csv(data_path)
        
        # 处理时间列
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)
        elif "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
        elif "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"])
            df.set_index("open_time", inplace=True)
        
        # 重命名列名以匹配backtesting.py要求
        column_mapping = {
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        df = df.rename(columns=column_mapping)
        
        # 过滤掉不需要的列
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        df = df[required_columns]
    elif data_format == "qlib":
        # 从QLib格式数据加载（简化实现，假设数据已转换为CSV）
        # 完整实现需要处理QLib的二进制数据格式
        qlib_data_path = Path(data_path) / symbol / "1d" / "close.bin"
        if not qlib_data_path.exists():
            raise FileNotFoundError(f"QLib数据文件不存在: {qlib_data_path}")
        # TODO: 实现QLib数据加载
        raise NotImplementedError("QLib数据格式加载尚未实现")
    else:
        raise ValueError(f"不支持的数据格式: {data_format}")
    
    # 过滤时间范围
    start_time = config.get("start_time")
    end_time = config.get("end_time")
    
    if start_time:
        start_time = pd.to_datetime(start_time)
        df = df[df.index >= start_time]
    
    if end_time:
        end_time = pd.to_datetime(end_time)
        df = df[df.index <= end_time]
    
    print(f"数据加载完成，共 {len(df)} 条记录")
    print(f"时间范围: {df.index[0]} 至 {df.index[-1]}")
    
    return df


def load_strategy(config):
    """
    加载策略
    
    Args:
        config: 配置字典
        
    Returns:
        type: 策略类
    """
    strategy_file = config.get("strategy", {}).get("file")
    strategy_class_name = config.get("strategy", {}).get("class")
    
    if not strategy_file:
        # 如果没有指定策略文件，使用默认策略
        strategy_file = str(Path(__file__).parent / "strategies" / "sma_cross.py")
    else:
        # 处理相对路径，相对于脚本所在目录解析
        strategy_path = Path(strategy_file)
        if not strategy_path.is_absolute():
            strategy_file = str(Path(__file__).parent / strategy_path)

    print(f"加载策略: {strategy_file}")
    
    # 动态导入策略模块
    spec = importlib.util.spec_from_file_location("strategy_module", strategy_file)
    if not spec or not spec.loader:
        raise ImportError(f"无法加载策略文件: {strategy_file}")
    
    strategy_module = importlib.util.module_from_spec(spec)
    sys.modules["strategy_module"] = strategy_module
    spec.loader.exec_module(strategy_module)
    
    # 获取策略类
    try:
        strategy_class = getattr(strategy_module, strategy_class_name)
    except AttributeError:
        raise AttributeError(f"策略文件中未找到策略类: {strategy_class_name}")
    
    print(f"策略加载完成: {strategy_class.__name__}")
    
    return strategy_class


def run_backtest(data, strategy_class, config):
    """
    执行回测
    
    Args:
        data: K线数据
        strategy_class: 策略类
        config: 配置字典
        
    Returns:
        tuple: 回测统计结果和Backtest对象
    """
    # 获取回测配置
    initial_cash = config.get("backtest", {}).get("initial_cash")
    commission = config.get("backtest", {}).get("commission")
    
    print(f"开始回测")
    print(f"初始资金: {initial_cash}")
    print(f"手续费率: {commission}")
    
    # 初始化回测，使用FractionalBacktest支持分数交易
    bt = Backtest(
        data,
        strategy_class,
        cash=initial_cash,
        commission=commission,
        exclusive_orders=True
    )
    
    # 获取策略参数
    strategy_params = config.get("strategy", {}).get("params", {})
    if strategy_params:
        print(f"使用策略参数: {strategy_params}")
    
    # 运行回测
    stats = bt.run(**strategy_params)
    
    print(f"回测完成")
    
    return stats, bt


def format_results(stats, bt):
    """
    格式化回测结果
    
    Args:
        stats: 回测统计结果
        bt: Backtest对象
        
    Returns:
        dict: 格式化后的结果
    """
    # 提取核心指标
    metrics = {
        "基础指标": {
            "起始时间": stats.get("Start").strftime("%Y-%m-%d %H:%M:%S"),
            "结束时间": stats.get("End").strftime("%Y-%m-%d %H:%M:%S"),
            "策略运行时间": str(stats.get("Duration")),
            "最终权益": stats.get("Equity Final [$]"),
            "权益峰值": stats.get("Equity Peak [$]"),
        },
        "收益与风险": {
            "总收益率": f"{stats.get('Return [%]', 0):.2f}%",
            "年化收益率": f"{stats.get('Return (Ann.) [%]', 0):.2f}%",
            "买入持有收益率": f"{stats.get('Buy & Hold Return [%]', 0):.2f}%",
            "最大回撤": f"{stats.get('Max. Drawdown [%]', 0):.2f}%",
            "夏普比率": f"{stats.get('Sharpe Ratio', 0):.2f}",
            "索提诺比率": f"{stats.get('Sortino Ratio', 0):.2f}",
            "卡尔马比率": f"{stats.get('Calmar Ratio', 0):.2f}",
        },
        "交易统计": {
            "交易次数": stats.get("# Trades", 0),
            "胜率": f"{stats.get('Win Rate [%]', 0):.2f}%",
            "平均持仓时间": str(stats.get("Avg. Trade Duration")),
            "最大持仓时间": str(stats.get("Max. Trade Duration")),
            "利润因子": f"{stats.get('Profit Factor', 0):.2f}",
        }
    }
    
    # 提取交易记录
    trades = []
    if "_trades" in stats:
        trade_df = stats["_trades"]
        for _, trade in trade_df.iterrows():
            trades.append({
                translator.get("entry_time"): trade.EntryTime.strftime("%Y-%m-%d %H:%M:%S"),
                translator.get("exit_time"): trade.ExitTime.strftime("%Y-%m-%d %H:%M:%S"),
                translator.get("hold_time"): str(trade.Duration),
                translator.get("entry_price"): round(trade.EntryPrice, 2),
                translator.get("exit_price"): round(trade.ExitPrice, 2),
                translator.get("position_size"): round(trade.Size, 2),
                translator.get("pnl"): round(trade.PnL, 2),
                translator.get("return_pct"): f"{trade.ReturnPct:.2f}%",
                translator.get("direction"): translator.get("long") if trade.Size > 0 else translator.get("short")
            })
    
    return {
        "metrics": metrics,
        "trades": trades,
        "raw_stats": stats.to_dict()
    }


def output_results(results, config):
    """
    输出回测结果
    
    Args:
        results: 格式化后的回测结果
        config: 配置字典
    """
    output_path = config.get("output", {}).get("path")
    output_format = config.get("output", {}).get("format", "console")
    
    if output_format == "json" and output_path:
        # 输出到JSON文件
        
        def json_serializer(obj):
            """
            自定义JSON序列化器，处理非序列化对象
            """
            from datetime import datetime, date
            import pandas as pd
            
            # 处理pandas Timestamp对象
            if isinstance(obj, pd.Timestamp):
                return obj.strftime("%Y-%m-%d %H:%M:%S")
            # 处理datetime对象
            elif isinstance(obj, (datetime, date)):
                return obj.strftime("%Y-%m-%d %H:%M:%S")
            # 处理其他非序列化对象，转换为字符串
            else:
                return str(obj)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=json_serializer)
        print(f"结果已输出到: {output_path}")
    else:
        # 控制台输出
        print("\n" + "=" * 60)
        print("回测结果概览")
        print("=" * 60)
        
        # 输出核心指标
        for category, metrics in results["metrics"].items():
            print(f"\n{category}:")
            print("-" * 30)
            for name, value in metrics.items():
                print(f"{name:<15}: {value}")
        
        # 输出交易记录
        print("\n" + "=" * 60)
        print("交易记录")
        print("=" * 60)
        
        if results["trades"]:
            # 打印交易记录表格
            print(f"{'入场时间':<20} {'出场时间':<20} {'方向':<8} {'收益率':<10} {'盈亏金额':<12} {'仓位大小':<10}")
            print("-" * 80)
            for trade in results["trades"]:
                print(f"{trade['入场时间']:<20} {trade['出场时间']:<20} {trade['方向']:<8} {trade['收益率']:<10} {trade['盈亏金额']:<12} {trade['仓位大小']:<10}")
            print(f"\n总交易次数: {len(results['trades'])}")
        else:
            print("没有交易记录")


def create_example_strategy():
    """
    创建示例策略文件
    """
    strategy_dir = Path(__file__).parent / "strategies"
    strategy_file = strategy_dir / "sma_cross.py"
    
    if not strategy_file.exists():
        strategy_content = '''from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd


class SmaCross(Strategy):
    """
    基于SMA交叉的策略
    当短期移动平均线上穿长期移动平均线时买入
    当短期移动平均线下穿长期移动平均线时卖出
    """
    # 策略参数
    n1 = 10  # 短期移动平均线周期
    n2 = 20  # 长期移动平均线周期
    
    def init(self):
        """初始化策略"""
        # 计算短期和长期移动平均线
        self.sma1 = self.I(self.compute_sma, self.data.Close, self.n1)
        self.sma2 = self.I(self.compute_sma, self.data.Close, self.n2)
    
    def compute_sma(self, data, period):
        """
        计算简单移动平均线
        
        :param data: 价格数据
        :param period: 周期
        :return: 移动平均线
        """
        return pd.Series(data).rolling(period).mean()
    
    def next(self):
        """每根K线执行一次"""
        # 当短期均线上穿长期均线时买入
        if crossover(self.sma1, self.sma2):
            self.buy()
        # 当短期均线下穿长期均线时卖出
        elif crossover(self.sma2, self.sma1):
            self.sell()
'''
        
        with open(strategy_file, "w", encoding="utf-8") as f:
            f.write(strategy_content)
        print(f"创建示例策略文件: {strategy_file}")


def create_example_config():
    """
    创建示例配置文件
    """
    config_file = Path(__file__).parent / "config.example.yaml"
    
    if not config_file.exists():
        config_content = '''# 回测配置示例

# 交易对
symbol: BTCUSDT

# 回测时间范围
start_time: "2023-01-01"
end_time: "2023-12-31"

# 策略配置
strategy:
  file: ./strategies/sma_cross.py
  class: SmaCross
  params:
    n1: 10  # 短期移动平均线周期
    n2: 20  # 长期移动平均线周期

# 数据配置
data:
  path: ../test_data/BTCUSDT.csv
  format: csv

# 回测配置
backtest:
  initial_cash: 10000  # 初始资金
  commission: 0.001     # 手续费率

# 输出配置
output:
  path: ./results/btc_sma_cross.json
  format: console  # json 或 console
'''
        
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)
        print(f"创建示例配置文件: {config_file}")


def main():
    """
    主函数
    """
    print("=" * 60)
    print("独立回测测试脚本")
    print("=" * 60)
    
    try:
        # 解析命令行参数
        args = parse_args()
        
        # 根据命令行参数更新翻译器语言
        global translator
        translator = Translator(args.lang)
        
        # 创建示例文件
        create_example_strategy()
        create_example_config()
        
        # 加载配置
        config = load_config(args)
        
        # 加载数据
        data = load_data(config)
        
        # 加载策略
        strategy_class = load_strategy(config)
        
        # 执行回测
        stats, bt = run_backtest(data, strategy_class, config)
        
        # 格式化结果
        results = format_results(stats, bt)
        
        # 输出结果
        output_results(results, config)
        
        print("\n" + "=" * 60)
        print("回测流程完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
