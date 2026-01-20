/**
 * 策略代理页面数据导出功能
 * 功能：将策略代理页面数据导出为HTML格式文件
 */

/**
 * 生成策略代理页面的HTML报告
 * @param data 导出数据，包含策略列表、选中策略详情等信息
 * @returns 生成的HTML字符串
 */
export const generateStrategyAgentReportHtml = (data: any) => {
  return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>策略代理报告 - ${new Date().toLocaleString()}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; color: #1f2937; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { margin-bottom: 24px; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); }
        .header h1 { margin: 0; font-size: 24px; color: #1890ff; }
        .header p { margin: 8px 0 0 0; color: #666; font-size: 14px; }
        .panel { background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); margin-bottom: 24px; overflow: hidden; }
        .panel-header { padding: 16px 24px; border-bottom: 1px solid #f0f0f0; background: #fafafa; font-weight: 600; font-size: 16px; }
        .panel-body { padding: 24px; }
        
        /* Grid Layouts */
        .strategy-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }
        .overview-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        .full-width { grid-column: 1 / -1; }
        
        /* Strategy Card */
        .strategy-card { background: #fafafa; padding: 16px; border-radius: 6px; border: 1px solid #e8e8e8; }
        .strategy-card h3 { margin: 0 0 8px 0; font-size: 16px; }
        .strategy-card .status { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; margin-bottom: 12px; }
        .status-active { background-color: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
        .status-paused { background-color: #fff7e6; color: #fa8c16; border: 1px solid #ffd591; }
        .status-inactive { background-color: #f5f5f5; color: #8c8c8c; border: 1px solid #d9d9d9; }
        .strategy-card .meta { margin-top: 8px; font-size: 12px; color: #6b7280; }
        .strategy-card .meta-item { display: block; margin-bottom: 4px; }
        .strategy-card .return { margin-top: 12px; font-size: 14px; }
        .return-positive { color: #52c41a; font-weight: 500; }
        .return-negative { color: #ff4d4f; font-weight: 500; }
        
        /* Charts */
        .chart-container { height: 400px; width: 100%; }
        .chart-container.small { height: 300px; }
        
        /* Table */
        .table-container { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }
        th { background: #fafafa; font-weight: 600; }
        tr:hover { background: #fafafa; }
        .text-center { text-align: center; }
        .text-right { text-align: right; }
        
        /* Pagination */
        .pagination { display: flex; justify-content: flex-end; align-items: center; margin-top: 16px; gap: 8px; }
        .pagination button { padding: 6px 12px; border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; cursor: pointer; }
        .pagination button:disabled { background: #f5f5f5; cursor: not-allowed; color: #bfbfbf; }
        .pagination button:hover:not(:disabled) { color: #40a9ff; border-color: #40a9ff; }
        .pagination select { padding: 6px; border-radius: 4px; border: 1px solid #d9d9d9; }
        
        /* Metrics */
        .metric-card { text-align: center; padding: 16px; background: #fafafa; border-radius: 6px; }
        .metric-card .label { font-size: 12px; color: #6b7280; display: block; margin-bottom: 4px; }
        .metric-card .value { font-weight: 600; font-size: 18px; }
        
        /* Empty State */
        .empty-state { text-align: center; padding: 40px 0; color: #999; font-size: 14px; }
        
        @media (max-width: 768px) {
            .container { padding: 12px; }
            .overview-grid { grid-template-columns: 1fr; }
            .strategy-grid { grid-template-columns: 1fr; }
            .metrics-grid { grid-template-columns: repeat(2, 1fr); }
            .chart-container { height: 300px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>策略代理报告</h1>
            <p>生成时间: ${new Date().toLocaleString()}</p>
        </div>

        <!-- 选中策略详情 -->
        <div class="panel" id="selected-strategy-panel">
            <div class="panel-header">策略详情</div>
            <div class="panel-body">
                <div class="overview-grid">
                    <!-- Strategy Info -->
                    <div id="strategy-info">
                        <!-- Injected via JS -->
                    </div>
                    
                    <!-- Return Rate Chart -->
                    <div>
                        <div class="chart-container" id="return-rate-chart"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 交易记录 -->
        <div class="panel" id="trades-panel">
            <div class="panel-header">交易记录</div>
            <div class="panel-body">
                <div class="table-container">
                    <table id="trades-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>交易对</th>
                                <th>类型</th>
                                <th>价格</th>
                                <th>数量</th>
                                <th>金额</th>
                                <th>状态</th>
                            </tr>
                        </thead>
                        <tbody id="trades-body"></tbody>
                    </table>
                </div>
                <div class="pagination">
                    <select id="page-size-select" onchange="changePageSize()">
                        <option value="10">10 条/页</option>
                        <option value="20">20 条/页</option>
                        <option value="50">50 条/页</option>
                    </select>
                    <span id="page-info">第 1 页</span>
                    <button id="prev-btn" onclick="prevPage()">上一页</button>
                    <button id="next-btn" onclick="nextPage()">下一页</button>
                </div>
            </div>
        </div>

        <!-- 性能指标 -->
        <div class="panel" id="performance-panel">
            <div class="panel-header">性能指标</div>
            <div class="panel-body">
                <div class="metrics-grid" id="performance-grid">
                    <!-- Injected via JS -->
                </div>
            </div>
        </div>
    </div>

    <script>
        // Inject Data
        const STRATEGY_AGENT_DATA = ${JSON.stringify(data)};
        
        // State
        let currentPage = 1;
        let pageSize = 10;
        
        // --- Initialization ---
        window.onload = function() {
            renderSelectedStrategy();
            renderTradesTable();
            renderPerformanceMetrics();
        };

        // --- Render Functions ---

        function renderSelectedStrategy() {
            const selectedStrategy = STRATEGY_AGENT_DATA.selectedStrategy;
            if (!selectedStrategy) return;
            
            // Strategy Info
            const infoContainer = document.getElementById('strategy-info');
            const statusClass = "status-" + selectedStrategy.status;
            
            infoContainer.innerHTML = "<h3>" + selectedStrategy.name + "</h3>" +
                "<p style=\"color: #666; margin: 8px 0;\">" + selectedStrategy.description + "</p>" +
                "<div class=\"status " + statusClass + "\">" + selectedStrategy.statusText + "</div>" +
                "<div class=\"meta\">" +
                "<div class=\"meta-item\">创建时间: " + selectedStrategy.createdAt + "</div>" +
                "<div class=\"meta-item\">创建人: " + selectedStrategy.createdBy + "</div>" +
                (selectedStrategy.status === 'active' ? "<div class=\"meta-item\">启动时间: " + selectedStrategy.startTime + "</div>" : "") +
                "<div class=\"meta-item\">最后交易: " + (selectedStrategy.lastTradeTime || '暂无交易') + "</div>" +
                "</div>" +
                "<div class=\"return\">" +
                "<div>总收益率: <span class=\"" + (selectedStrategy.totalReturn >= 0 ? 'return-positive' : 'return-negative') + "\">" + selectedStrategy.totalReturn.toFixed(2) + "%</span></div>" +
                "<div>今日收益: <span class=\"" + (selectedStrategy.currentReturn >= 0 ? 'return-positive' : 'return-negative') + "\">" + selectedStrategy.currentReturn.toFixed(2) + "%</span></div>" +
                "</div>";
            
            // Render return rate chart
            renderReturnRateChart(selectedStrategy);
        }

        function renderReturnRateChart(strategy) {
            if (!strategy.returnRateData || strategy.returnRateData.length === 0) return;
            
            const chart = echarts.init(document.getElementById('return-rate-chart'));
            const dates = strategy.returnRateData.map(item => item.timestamp);
            const values = strategy.returnRateData.map(item => item.value);
            
            const option = {
                title: {
                    text: '收益率曲线',
                    left: 'center',
                    textStyle: { fontSize: 14 }
                },
                tooltip: {
                    trigger: 'axis',
                    formatter: (params) => {
                        const data = params[0];
                        return \`\${data.name}<br/>收益率: \${data.value.toFixed(2)}%\`;
                    }
                },
                grid: {
                    left: '3%',
                    right: '4%',
                    bottom: '3%',
                    containLabel: true
                },
                xAxis: {
                    type: 'category',
                    boundaryGap: false,
                    data: dates,
                    axisLabel: { fontSize: 10, rotate: 45 }
                },
                yAxis: {
                    type: 'value',
                    axisLabel: { formatter: '{value}%' }
                },
                series: [{
                    name: '收益率',
                    type: 'line',
                    smooth: true,
                    data: values,
                    lineStyle: {
                        color: strategy.currentReturn >= 0 ? '#52c41a' : '#ff4d4f',
                        width: 2
                    },
                    areaStyle: {
                        color: {
                            type: 'linear',
                            x: 0,
                            y: 0,
                            x2: 0,
                            y2: 1,
                            colorStops: [
                                {
                                    offset: 0,
                                    color: strategy.currentReturn >= 0 ? 'rgba(82, 196, 26, 0.3)' : 'rgba(255, 77, 79, 0.3)'
                                },
                                {
                                    offset: 1,
                                    color: strategy.currentReturn >= 0 ? 'rgba(82, 196, 26, 0.1)' : 'rgba(255, 77, 79, 0.1)'
                                }
                            ]
                        }
                    },
                    itemStyle: {
                        color: strategy.currentReturn >= 0 ? '#52c41a' : '#ff4d4f'
                    }
                }]
            };
            
            chart.setOption(option);
            
            window.onresize = () => {
                chart.resize();
            };
        }

        function renderTradesTable() {
            const selectedStrategy = STRATEGY_AGENT_DATA.selectedStrategy;
            if (!selectedStrategy || !selectedStrategy.tradeRecords || selectedStrategy.tradeRecords.length === 0) {
                document.getElementById('trades-panel').style.display = 'none';
                return;
            }
            
            const tbody = document.getElementById('trades-body');
            const trades = selectedStrategy.tradeRecords;
            
            function renderTable() {
                tbody.innerHTML = '';
                
                const start = (currentPage - 1) * pageSize;
                const end = start + pageSize;
                const pageData = trades.slice(start, end);
                
                if (pageData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#999;">暂无交易记录</td></tr>';
                    return;
                }
                
                pageData.forEach(trade => {
                    const tr = document.createElement('tr');
                    const actionClass = trade.action === 'buy' ? 'return-positive' : 'return-negative';
                    const actionText = trade.action === 'buy' ? '买入' : '卖出';
                    const statusClass = {
                        'filled': 'status-active',
                        'pending': 'status-paused',
                        'canceled': 'status-inactive'
                    }[trade.status] || 'status-inactive';
                    const statusText = {
                        'filled': '已成交',
                        'pending': '挂单中',
                        'canceled': '已取消'
                    }[trade.status] || '未知';
                    
                    tr.innerHTML = "<td>" + trade.timestamp + "</td>" +
                        "<td>" + trade.symbol + "</td>" +
                        "<td class=\"" + actionClass + "\">" + actionText + "</td>" +
                        "<td>$" + trade.price.toFixed(2) + "</td>" +
                        "<td>" + trade.quantity.toFixed(4) + "</td>" +
                        "<td>$" + trade.amount.toFixed(2) + "</td>" +
                        "<td><span class=\"status " + statusClass + "\">" + statusText + "</span></td>";
                    tbody.appendChild(tr);
                });
                
                updatePagination();
            }
            
            function updatePagination() {
                const totalPages = Math.ceil(trades.length / pageSize);
                document.getElementById('page-info').innerText = "第 " + currentPage + " / " + (totalPages || 1) + " 页";
                document.getElementById('prev-btn').disabled = currentPage === 1;
                document.getElementById('next-btn').disabled = currentPage >= totalPages;
            }
            
            window.prevPage = function() {
                if (currentPage > 1) {
                    currentPage--;
                    renderTable();
                }
            };
            
            window.nextPage = function() {
                const totalPages = Math.ceil(trades.length / pageSize);
                if (currentPage < totalPages) {
                    currentPage++;
                    renderTable();
                }
            };
            
            window.changePageSize = function() {
                pageSize = parseInt(document.getElementById('page-size-select').value);
                currentPage = 1;
                renderTable();
            };
            
            renderTable();
        }

        function renderPerformanceMetrics() {
            const selectedStrategy = STRATEGY_AGENT_DATA.selectedStrategy;
            if (!selectedStrategy || !selectedStrategy.performance) {
                document.getElementById('performance-panel').style.display = 'none';
                return;
            }
            
            const container = document.getElementById('performance-grid');
            const performance = selectedStrategy.performance;
            
            const metrics = [
                { key: 'winRate', label: '胜率', suffix: '%' },
                { key: 'profitLossRatio', label: '盈亏比', suffix: '' },
                { key: 'maxDrawdown', label: '最大回撤', suffix: '%' },
                { key: 'sharpeRatio', label: '夏普比率', suffix: '' },
                { key: 'totalTrades', label: '总交易数', suffix: '' },
                { key: 'winningTrades', label: '盈利交易', suffix: '' },
                { key: 'losingTrades', label: '亏损交易', suffix: '' },
                { key: 'calmarRatio', label: '卡尔马比率', suffix: '' }
            ];
            
            metrics.forEach(metric => {
                if (performance[metric.key] !== undefined) {
                    const div = document.createElement('div');
                    div.className = 'metric-card';
                    const value = typeof performance[metric.key] === 'number' ? performance[metric.key].toFixed(2) : performance[metric.key];
                    div.innerHTML = "<span class=\"label\">" + metric.label + "</span>" +
                        "<span class=\"value\">" + value + metric.suffix + "</span>";
                    container.appendChild(div);
                }
            });
        }
    </script>
</body>
</html>
  `;
};

/**
 * 导出策略代理页面数据为HTML文件
 * @param data 导出数据
 * @param filename 文件名
 */
export const exportStrategyAgentToHtml = (data: any, filename: string = 'strategy-agent-report.html') => {
  const htmlContent = generateStrategyAgentReportHtml(data);
  const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  
  URL.revokeObjectURL(url);
};