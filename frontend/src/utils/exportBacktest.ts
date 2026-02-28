/**
 * 回测报告导出工具函数
 * 功能：将回测结果导出为HTML报告
 */

export const generateBacktestReportHtml = (data: any) => {
  return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>回测报告 - ${data.strategy_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; color: #1f2937; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { margin-bottom: 24px; }
        .header h1 { margin: 0; font-size: 24px; }
        .panel { background: #fff; border-radius: 8px; box-shadow: 0 1px 2px 0 rgba(0,0,0,0.03); margin-bottom: 24px; overflow: hidden; }
        .panel-header { padding: 16px 24px; border-bottom: 1px solid #f0f0f0; background: #fafafa; font-weight: 600; font-size: 16px; }
        .panel-body { padding: 24px; }
        
        /* Grid Layouts */
        .config-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
        .overview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }
        .grid-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        
        /* Items */
        .config-item { background: #fafafa; padding: 12px; border-radius: 6px; }
        .config-item .label { font-size: 12px; color: #6b7280; display: block; margin-bottom: 4px; }
        .config-item .value { font-weight: 500; font-size: 14px; word-break: break-all; }
        .config-item.full-width { grid-column: 1 / -1; }
        
        .metric-card { background: #fafafa; padding: 16px; border-radius: 6px; text-align: center; }
        .metric-label { font-size: 12px; color: #6b7280; margin-bottom: 8px; }
        .metric-value { font-size: 24px; font-weight: 600; }
        .positive { color: #10b981; }
        .negative { color: #ef4444; }
        
        /* Charts */
        .chart-container { height: 400px; width: 100%; }
        .chart-container.small { height: 300px; }
        
        /* Table */
        .table-container { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }
        th { background: #fafafa; font-weight: 600; }
        tr:hover { background: #fafafa; }
        
        /* Pagination */
        .pagination { display: flex; justify-content: flex-end; align-items: center; margin-top: 16px; gap: 8px; }
        .pagination button { padding: 6px 12px; border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; cursor: pointer; }
        .pagination button:disabled { background: #f5f5f5; cursor: not-allowed; color: #bfbfbf; }
        .pagination button:hover:not(:disabled) { color: #40a9ff; border-color: #40a9ff; }
        .pagination select { padding: 6px; border-radius: 4px; border: 1px solid #d9d9d9; }

        pre { background: #eee; padding: 10px; border-radius: 4px; overflow-x: auto; margin: 0; }
        
        @media (max-width: 768px) {
            .grid-layout { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>回测报告: ${data.strategy_name}</h1>
            <p style="color: #666; font-size: 14px; margin-top: 8px;">生成时间: ${new Date().toLocaleString()}</p>
        </div>

        <!-- Configuration -->
        <div class="panel">
            <div class="panel-header">配置信息</div>
            <div class="panel-body">
                <div class="config-grid">
                    <div class="config-item">
                        <span class="label">策略名称</span>
                        <span class="value">${data.strategy_name}</span>
                    </div>
                    <div class="config-item">
                        <span class="label">交易标的</span>
                        <span class="value">${Array.isArray(data.backtest_config.symbols) ? data.backtest_config.symbols.join(', ') : data.backtest_config.symbols}</span>
                    </div>
                    <div class="config-item">
                        <span class="label">时间范围</span>
                        <span class="value">${data.backtest_config.start_time} ~ ${data.backtest_config.end_time}</span>
                    </div>
                    <div class="config-item">
                        <span class="label">周期</span>
                        <span class="value">${data.backtest_config.interval}</span>
                    </div>
                    <div class="config-item">
                        <span class="label">初始资金</span>
                        <span class="value">${data.backtest_config.initial_cash}</span>
                    </div>
                    <div class="config-item">
                        <span class="label">手续费率</span>
                        <span class="value">${data.backtest_config.commission}</span>
                    </div>
                    ${data.strategy_config?.params ? `
                    <div class="config-item full-width">
                        <span class="label">策略参数</span>
                        <pre class="value">${JSON.stringify(data.strategy_config.params, null, 2)}</pre>
                    </div>
                    ` : ''}
                </div>
            </div>
        </div>

        <!-- Overview -->
        <div class="panel">
            <div class="panel-header">回测概览</div>
            <div class="panel-body">
                <div class="overview-grid" id="overview-grid">
                    <!-- Injected via JS -->
                </div>
            </div>
        </div>

        <!-- Performance Chart -->
        <div class="panel">
            <div class="panel-header">绩效分析</div>
            <div class="panel-body">
                <div id="return-chart" class="chart-container"></div>
            </div>
        </div>

        <div class="grid-layout">
            <!-- Trades Table -->
            <div class="panel">
                <div class="panel-header">交易详情</div>
                <div class="panel-body">
                    <div class="table-container">
                        <table id="trades-table">
                            <thead>
                                <tr>
                                    <th>入场时间</th>
                                    <th>出场时间</th>
                                    <th>方向</th>
                                    <th>入场价格</th>
                                    <th>出场价格</th>
                                    <th>仓位</th>
                                    <th>收益</th>
                                    <th>收益率</th>
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
                            <option value="100">100 条/页</option>
                        </select>
                        <span id="page-info">第 1 页</span>
                        <button id="prev-btn" onclick="prevPage()">上一页</button>
                        <button id="next-btn" onclick="nextPage()">下一页</button>
                    </div>
                </div>
            </div>

            <!-- Risk Analysis -->
            <div class="panel">
                <div class="panel-header">风险分析</div>
                <div class="panel-body">
                    <div class="overview-grid" id="risk-grid" style="grid-template-columns: 1fr 1fr; margin-bottom: 20px;">
                        <!-- Injected via JS -->
                    </div>
                    <div id="risk-chart" class="chart-container small"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Inject Data
        const BACKTEST_DATA = ${JSON.stringify(data)};
        
        // State
        let currentPage = 1;
        let pageSize = 10;
        
        // --- Initialization ---
        window.onload = function() {
            renderOverview();
            renderCharts();
            renderTable();
            renderRiskMetrics();
        };

        // --- Render Functions ---
        function renderOverview() {
            const keyMetrics = ['总收益率', '年化收益率', '最大回撤', '夏普比率', '胜率', '交易次数'];
            const container = document.getElementById('overview-grid');
            
            BACKTEST_DATA.metrics.forEach(metric => {
                if (keyMetrics.includes(metric.name)) {
                    const div = document.createElement('div');
                    div.className = 'metric-card';
                    const isReturn = metric.key === 'Return [%]';
                    const value = Number(metric.value);
                    const colorClass = isReturn ? (value >= 0 ? 'positive' : 'negative') : '';
                    const displayValue = typeof metric.value === 'number' ? metric.value.toFixed(2) + (isReturn || metric.name.includes('率') ? '%' : '') : metric.value;
                    
                    div.innerHTML = \`
                        <div class="metric-label">\${metric.name}</div>
                        <div class="metric-value \${colorClass}">\${displayValue}</div>
                    \`;
                    container.appendChild(div);
                }
            });
        }

        function renderRiskMetrics() {
            const riskMetrics = ['波动率', '索提诺比率', '卡尔马比率', '信息比率'];
            const container = document.getElementById('risk-grid');
            
            BACKTEST_DATA.metrics.forEach(metric => {
                if (riskMetrics.includes(metric.name)) {
                    const div = document.createElement('div');
                    div.className = 'metric-card';
                    div.style.padding = '12px';
                    div.innerHTML = \`
                        <div class="metric-label">\${metric.name}</div>
                        <div class="metric-value" style="font-size: 18px;">\${typeof metric.value === 'number' ? metric.value.toFixed(2) : metric.value}</div>
                    \`;
                    container.appendChild(div);
                }
            });
        }

        function renderCharts() {
            // Equity Curve
            const equityChart = echarts.init(document.getElementById('return-chart'));
            const dates = BACKTEST_DATA.equity_curve.map(item => item.datetime || item.Open_time || '').filter(d => d);
            const equity = BACKTEST_DATA.equity_curve.map(item => item.Equity || 0);
            
            equityChart.setOption({
                tooltip: { trigger: 'axis' },
                xAxis: { type: 'category', data: dates },
                yAxis: { type: 'value', scale: true },
                dataZoom: [{ type: 'inside' }, { type: 'slider' }],
                series: [{
                    data: equity,
                    type: 'line',
                    smooth: true,
                    areaStyle: {
                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                            { offset: 0, color: 'rgba(74, 108, 247, 0.3)' },
                            { offset: 1, color: 'rgba(74, 108, 247, 0.05)' }
                        ])
                    },
                    itemStyle: { color: '#4a6cf7' }
                }]
            });

            // Risk Chart (Max Drawdown)
            const riskChart = echarts.init(document.getElementById('risk-chart'));
            const maxDrawdown = BACKTEST_DATA.metrics.find(m => m.cn_name === '最大回撤')?.value || 0;
            
            riskChart.setOption({
                title: { text: '最大回撤', left: 'center', textStyle: { fontSize: 14 } },
                tooltip: { trigger: 'item' },
                xAxis: { type: 'category', data: ['最大回撤'] },
                yAxis: { type: 'value' },
                series: [{
                    data: [maxDrawdown],
                    type: 'bar',
                    itemStyle: { color: '#f87272' },
                    label: { show: true, position: 'top', formatter: '{c}%' }
                }]
            });
            
            window.onresize = () => {
                equityChart.resize();
                riskChart.resize();
            };
        }

        function renderTable() {
            const tbody = document.getElementById('trades-body');
            tbody.innerHTML = '';
            
            const start = (currentPage - 1) * pageSize;
            const end = start + pageSize;
            const pageData = BACKTEST_DATA.trades.slice(start, end);
            
            if (pageData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:#999;">暂无数据</td></tr>';
                return;
            }

            pageData.forEach(trade => {
                const tr = document.createElement('tr');
                const pnlClass = trade.PnL >= 0 ? 'positive' : 'negative';
                const pnlSign = trade.PnL >= 0 ? '+' : '';
                
                tr.innerHTML = \`
                    <td>\${trade.EntryTime}</td>
                    <td>\${trade.ExitTime}</td>
                    <td>\${trade.Direction}</td>
                    <td>\${trade.EntryPrice.toFixed(2)}</td>
                    <td>\${trade.ExitPrice.toFixed(2)}</td>
                    <td>\${trade.Size}</td>
                    <td class="\${pnlClass}">\${pnlSign}\${trade.PnL.toFixed(2)}</td>
                    <td class="\${pnlClass}">\${pnlSign}\${trade.ReturnPct.toFixed(2)}%</td>
                \`;
                tbody.appendChild(tr);
            });
            
            updatePagination();
        }

        // --- Pagination Logic ---
        function updatePagination() {
            const totalPages = Math.ceil(BACKTEST_DATA.trades.length / pageSize);
            document.getElementById('page-info').innerText = \`第 \${currentPage} / \${totalPages || 1} 页\`;
            document.getElementById('prev-btn').disabled = currentPage === 1;
            document.getElementById('next-btn').disabled = currentPage >= totalPages;
        }

        function prevPage() {
            if (currentPage > 1) {
                currentPage--;
                renderTable();
            }
        }

        function nextPage() {
            const totalPages = Math.ceil(BACKTEST_DATA.trades.length / pageSize);
            if (currentPage < totalPages) {
                currentPage++;
                renderTable();
            }
        }

        function changePageSize() {
            pageSize = parseInt(document.getElementById('page-size-select').value);
            currentPage = 1;
            renderTable();
        }
    </script>
</body>
</html>
  `;
};
