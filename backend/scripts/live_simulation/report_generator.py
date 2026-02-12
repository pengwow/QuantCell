"""
报告生成器

生成测试结果报告，包含策略表现分析、框架响应时间等关键指标。
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import statistics

from .models import SimulationMetrics, TradeSignal, OrderInfo


@dataclass
class ReportData:
    """报告数据"""
    # 基本信息
    report_name: str
    generated_at: datetime = field(default_factory=datetime.now)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # 模拟配置
    config: Dict[str, Any] = field(default_factory=dict)
    
    # 性能指标
    metrics: SimulationMetrics = field(default_factory=SimulationMetrics)
    
    # 交易统计
    signals: List[TradeSignal] = field(default_factory=list)
    orders: List[OrderInfo] = field(default_factory=list)
    
    # 异常记录
    exceptions: List[Dict[str, Any]] = field(default_factory=list)
    
    # 附加数据
    extra_data: Dict[str, Any] = field(default_factory=dict)


class BaseReportGenerator(ABC):
    """报告生成器基类"""
    
    @abstractmethod
    def generate(self, data: ReportData, output_path: str):
        """生成报告"""
        pass


class JSONReportGenerator(BaseReportGenerator):
    """JSON报告生成器"""
    
    def generate(self, data: ReportData, output_path: str):
        """生成JSON报告"""
        report = {
            "report_name": data.report_name,
            "generated_at": data.generated_at.isoformat(),
            "start_time": data.start_time.isoformat() if data.start_time else None,
            "end_time": data.end_time.isoformat() if data.end_time else None,
            "config": data.config,
            "metrics": data.metrics.to_dict(),
            "signals_count": len(data.signals),
            "orders_count": len(data.orders),
            "exceptions_count": len(data.exceptions),
            "extra_data": data.extra_data,
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)


class HTMLReportGenerator(BaseReportGenerator):
    """HTML报告生成器"""
    
    def generate(self, data: ReportData, output_path: str):
        """生成HTML报告"""
        html_content = self._build_html(data)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    
    def _build_html(self, data: ReportData) -> str:
        """构建HTML内容"""
        metrics = data.metrics
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{data.report_name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .metric-card {{
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #4CAF50;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin-top: 5px;
        }}
        .positive {{
            color: #4CAF50;
        }}
        .negative {{
            color: #f44336;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .info {{
            background-color: #e3f2fd;
            padding: 15px;
            border-radius: 6px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{data.report_name}</h1>
        
        <div class="info">
            <strong>生成时间:</strong> {data.generated_at.strftime('%Y-%m-%d %H:%M:%S')}<br>
            <strong>测试时长:</strong> {metrics.total_duration_ms / 1000:.2f} 秒<br>
            <strong>数据点数:</strong> {metrics.total_data_points}
        </div>
        
        <h2>性能指标</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">总盈亏</div>
                <div class="metric-value {'positive' if metrics.total_pnl >= 0 else 'negative'}">{metrics.total_pnl:+.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">已实现盈亏</div>
                <div class="metric-value {'positive' if metrics.realized_pnl >= 0 else 'negative'}">{metrics.realized_pnl:+.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">未实现盈亏</div>
                <div class="metric-value {'positive' if metrics.unrealized_pnl >= 0 else 'negative'}">{metrics.unrealized_pnl:+.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">最大回撤</div>
                <div class="metric-value negative">{metrics.max_drawdown:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">夏普比率</div>
                <div class="metric-value">{metrics.sharpe_ratio:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">平均延迟</div>
                <div class="metric-value">{metrics.avg_latency_ms:.2f} ms</div>
            </div>
        </div>
        
        <h2>交易统计</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">交易信号</div>
                <div class="metric-value">{metrics.total_signals}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">订单总数</div>
                <div class="metric-value">{metrics.total_orders}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">已成交</div>
                <div class="metric-value">{metrics.filled_orders}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">成交率</div>
                <div class="metric-value">
                    {metrics.filled_orders / metrics.total_orders * 100:.1f}% 
                    if metrics.total_orders > 0 else 0%
                </div>
            </div>
        </div>
        
        <h2>异常统计</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">异常总数</div>
                <div class="metric-value">{metrics.exceptions_count}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">网络错误</div>
                <div class="metric-value">{metrics.network_errors}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">数据错误</div>
                <div class="metric-value">{metrics.data_errors}</div>
            </div>
        </div>
        
        <h2>配置信息</h2>
        <pre>{json.dumps(data.config, indent=2, ensure_ascii=False)}</pre>
    </div>
</body>
</html>
"""
        return html


class ReportGenerator:
    """报告生成器管理类"""
    
    def __init__(self):
        self._generators: Dict[str, BaseReportGenerator] = {
            "json": JSONReportGenerator(),
            "html": HTMLReportGenerator(),
        }
    
    def generate_report(
        self,
        data: ReportData,
        output_dir: str,
        formats: Optional[List[str]] = None,
    ) -> List[str]:
        """
        生成报告
        
        Args:
            data: 报告数据
            output_dir: 输出目录
            formats: 报告格式列表，默认 ["json", "html"]
            
        Returns:
            生成的文件路径列表
        """
        if formats is None:
            formats = ["json", "html"]
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        generated_files = []
        
        for fmt in formats:
            if fmt not in self._generators:
                continue
                
            generator = self._generators[fmt]
            file_path = output_path / f"{data.report_name}.{fmt}"
            
            try:
                generator.generate(data, str(file_path))
                generated_files.append(str(file_path))
            except Exception as e:
                print(f"Failed to generate {fmt} report: {e}")
        
        return generated_files
    
    def register_generator(self, name: str, generator: BaseReportGenerator):
        """注册报告生成器"""
        self._generators[name] = generator


def create_report_generator() -> ReportGenerator:
    """创建报告生成器"""
    return ReportGenerator()
