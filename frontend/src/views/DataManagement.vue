<template>
  <div class="data-management-container">
    <header class="page-header">
      <h1>数据管理</h1>
    </header>

    <div class="data-management-content">
      <!-- 侧边栏导航 -->
      <aside class="data-management-sidebar">
        <nav class="data-management-nav">
          <ul>
            <li 
              v-for="menu in menuItems" 
              :key="menu.id"
              :class="{ active: currentTab === menu.id }"
              @click="currentTab = menu.id"
            >
              <i :class="menu.icon"></i>
              <span>{{ menu.title }}</span>
            </li>
          </ul>
        </nav>
      </aside>

      <!-- 主内容区域 -->
      <main class="data-management-main">
        <!-- 加密货币数据 -->
        <div v-if="currentTab === 'crypto'" class="data-panel">
          <h2>加密货币数据</h2>
          <div class="data-section">
            <div class="data-actions">
              <button class="btn btn-primary" @click="refreshCryptoData">刷新数据</button>
              <button class="btn btn-secondary" @click="exportCryptoData">导出数据</button>
            </div>
            
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>符号</th>
                    <th>当前价格</th>
                    <th>24h变化</th>
                    <th>市值</th>
                    <th>交易量</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="crypto in cryptoData" :key="crypto.id">
                    <td>{{ crypto.name }}</td>
                    <td>{{ crypto.symbol }}</td>
                    <td>${{ crypto.currentPrice.toLocaleString() }}</td>
                    <td :class="{ 'price-up': crypto.priceChange24h > 0, 'price-down': crypto.priceChange24h < 0 }">
                      {{ crypto.priceChange24h > 0 ? '+' : '' }}{{ crypto.priceChange24h.toFixed(2) }}%
                    </td>
                    <td>${{ formatNumber(crypto.marketCap) }}</td>
                    <td>${{ formatNumber(crypto.tradingVolume) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- 股票数据 -->
        <div v-if="currentTab === 'stock'" class="data-panel">
          <h2>股票数据</h2>
          <div class="data-section">
            <div class="data-actions">
              <button class="btn btn-primary" @click="refreshStockData">刷新数据</button>
              <button class="btn btn-secondary" @click="exportStockData">导出数据</button>
            </div>
            
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>公司名称</th>
                    <th>股票代码</th>
                    <th>当前价格</th>
                    <th>今日变化</th>
                    <th>开盘价</th>
                    <th>最高价</th>
                    <th>最低价</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="stock in stockData" :key="stock.symbol">
                    <td>{{ stock.companyName }}</td>
                    <td>{{ stock.symbol }}</td>
                    <td>${{ stock.currentPrice.toFixed(2) }}</td>
                    <td :class="{ 'price-up': stock.priceChange > 0, 'price-down': stock.priceChange < 0 }">
                      {{ stock.priceChange > 0 ? '+' : '' }}{{ stock.priceChange.toFixed(2) }} ({{ stock.priceChangePercent.toFixed(2) }}%)
                    </td>
                    <td>${{ stock.openPrice.toFixed(2) }}</td>
                    <td>${{ stock.highPrice.toFixed(2) }}</td>
                    <td>${{ stock.lowPrice.toFixed(2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- 数据导入 -->
        <div v-if="currentTab === 'import'" class="data-panel">
          <h2>数据导入</h2>
          <div class="data-section">
            <div class="import-form">
              <div class="form-row">
                <div class="form-group">
                  <label for="dataType">数据类型</label>
                  <select id="dataType" v-model="importForm.dataType" class="form-control">
                    <option value="crypto">加密货币</option>
                    <option value="stock">股票</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="exchange">交易所</label>
                  <select id="exchange" v-model="importForm.exchange" class="form-control">
                    <option value="binance">Binance</option>
                    <option value="okx">OKX</option>
                  </select>
                </div>
              </div>
              
              <div class="form-row">
                <div class="form-group">
                  <label for="startDate">开始日期</label>
                  <input type="date" id="startDate" v-model="importForm.startDate" class="form-control">
                </div>
                <div class="form-group">
                  <label for="endDate">结束日期</label>
                  <input type="date" id="endDate" v-model="importForm.endDate" class="form-control">
                </div>
              </div>
              
              <div class="form-row">
                <div class="form-group">
                  <label for="interval">时间间隔</label>
                  <select id="interval" v-model="importForm.interval" class="form-control">
                    <option value="1d">日线</option>
                    <option value="1h">小时线</option>
                    <option value="30m">30分钟线</option>
                    <option value="15m">15分钟线</option>
                    <option value="5m">5分钟线</option>
                    <option value="1m">1分钟线</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="symbols">交易对</label>
                  <input type="text" id="symbols" v-model="importForm.symbols" class="form-control" placeholder="如: BTCUSDT,ETHUSDT">
                </div>
              </div>
              
              <div class="form-row">
                <div class="form-group">
                  <label for="fileUpload">或上传文件</label>
                  <input type="file" id="fileUpload" @change="handleFileUpload" class="form-control-file" multiple>
                </div>
              </div>
              
              <div class="data-actions">
                <button class="btn btn-primary" @click="startImport">开始导入</button>
                <button class="btn btn-secondary" @click="resetImportForm">重置</button>
              </div>
            </div>
            
            <div v-if="importProgress > 0" class="import-progress">
              <div class="progress-bar-container">
                <div class="progress-bar" :style="{ width: importProgress + '%' }"></div>
              </div>
              <div class="progress-text">{{ importProgress }}%</div>
            </div>
            
            <div v-if="importLog.length > 0" class="import-log">
              <h3>导入日志</h3>
              <div class="log-content">
                <div v-for="(log, index) in importLog" :key="index" class="log-item">{{ log }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 数据质量检查 -->
        <div v-if="currentTab === 'quality'" class="data-panel">
          <h2>数据质量检查</h2>
          <div class="data-section">
            <div class="quality-check-form">
              <div class="form-row">
                <div class="form-group">
                  <label for="checkDataType">数据类型</label>
                  <select id="checkDataType" v-model="qualityForm.dataType" class="form-control">
                    <option value="crypto">加密货币</option>
                    <option value="stock">股票</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="checkSymbol">交易对/股票代码</label>
                  <input type="text" id="checkSymbol" v-model="qualityForm.symbol" class="form-control" placeholder="如: BTCUSDT 或 AAPL">
                </div>
              </div>
              
              <div class="form-row">
                <div class="form-group">
                  <label for="checkStartDate">开始日期</label>
                  <input type="date" id="checkStartDate" v-model="qualityForm.startDate" class="form-control">
                </div>
                <div class="form-group">
                  <label for="checkEndDate">结束日期</label>
                  <input type="date" id="checkEndDate" v-model="qualityForm.endDate" class="form-control">
                </div>
              </div>
              
              <div class="data-actions">
                <button class="btn btn-primary" @click="startQualityCheck">开始检查</button>
              </div>
            </div>
            
            <div v-if="qualityResult" class="quality-result">
              <h3>检查结果</h3>
              <div class="result-summary">
                <div class="result-item">
                  <span class="result-label">数据总量:</span>
                  <span class="result-value">{{ qualityResult.totalRows }}</span>
                </div>
                <div class="result-item">
                  <span class="result-label">缺失值数量:</span>
                  <span class="result-value" :class="{ 'result-warning': qualityResult.missingValues > 0 }">
                    {{ qualityResult.missingValues }}
                  </span>
                </div>
                <div class="result-item">
                  <span class="result-label">异常值数量:</span>
                  <span class="result-value" :class="{ 'result-warning': qualityResult.outliers > 0 }">
                    {{ qualityResult.outliers }}
                  </span>
                </div>
                <div class="result-item">
                  <span class="result-label">数据完整性:</span>
                  <span class="result-value" :class="resultClass(qualityResult.completeness)">
                    {{ qualityResult.completeness.toFixed(2) }}%
                  </span>
                </div>
              </div>
              
              <div class="quality-details">
                <h4>详细报告</h4>
                <div class="details-content" v-html="qualityResult.details"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- 数据可视化 -->
        <div v-if="currentTab === 'visualization'" class="data-panel">
          <h2>数据可视化</h2>
          <div class="data-section">
            <div class="visualization-form">
              <div class="form-row">
                <div class="form-group">
                  <label for="vizDataType">数据类型</label>
                  <select id="vizDataType" v-model="vizForm.dataType" class="form-control">
                    <option value="crypto">加密货币</option>
                    <option value="stock">股票</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="vizSymbol">交易对/股票代码</label>
                  <input type="text" id="vizSymbol" v-model="vizForm.symbol" class="form-control" placeholder="如: BTCUSDT 或 AAPL">
                </div>
              </div>
              
              <div class="form-row">
                <div class="form-group">
                  <label for="vizStartDate">开始日期</label>
                  <input type="date" id="vizStartDate" v-model="vizForm.startDate" class="form-control">
                </div>
                <div class="form-group">
                  <label for="vizEndDate">结束日期</label>
                  <input type="date" id="vizEndDate" v-model="vizForm.endDate" class="form-control">
                </div>
              </div>
              
              <div class="form-row">
                <div class="form-group">
                  <label for="vizChartType">图表类型</label>
                  <select id="vizChartType" v-model="vizForm.chartType" class="form-control">
                    <option value="candlestick">K线图</option>
                    <option value="line">折线图</option>
                    <option value="bar">柱状图</option>
                    <option value="area">面积图</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="vizIndicator">指标</label>
                  <select id="vizIndicator" v-model="vizForm.indicator" class="form-control">
                    <option value="close">收盘价</option>
                    <option value="volume">成交量</option>
                    <option value="open">开盘价</option>
                    <option value="high">最高价</option>
                    <option value="low">最低价</option>
                  </select>
                </div>
              </div>
              
              <div class="data-actions">
                <button class="btn btn-primary" @click="generateVisualization">生成图表</button>
                <button class="btn btn-secondary" @click="exportChart">导出图表</button>
              </div>
            </div>
            
            <div class="visualization-container">
              <div v-if="vizChartUrl" class="chart-container">
                <img :src="vizChartUrl" alt="数据可视化图表" class="chart-image">
              </div>
              <div v-else class="chart-placeholder">
                <div class="placeholder-content">
                  <i class="icon-chart"></i>
                  <p>请配置参数并点击"生成图表"按钮</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 资产池管理 -->
        <div v-if="currentTab === 'asset-pools'" class="data-panel">
          <h2>资产池管理</h2>
          <div class="data-section">
            <!-- 资产池管理组件 -->
            <asset-pool-manager></asset-pool-manager>
          </div>
        </div>

        <!-- 数据采集 -->
        <div v-if="currentTab === 'collection'" class="data-panel">
          <h2>数据采集</h2>
          
          <!-- 数据加载表单 -->
          <div class="data-section">
            <h3>数据获取</h3>
            <div class="import-form">
              <!-- 第一行：品种和周期 -->
              <div class="form-row">
                <div class="form-group">
                  <label for="symbols">品种</label>
                  <el-select
                    v-model="collectionForm.symbols"
                    multiple
                    filterable
                    allow-create
                    clearable
                    placeholder="请选择品种"
                    class="form-control"
                  >
                    <el-option value="BTCUSDT" label="BTCUSDT" />
                    <el-option value="ETHUSDT" label="ETHUSDT" />
                    <el-option value="BNBUSDT" label="BNBUSDT" />
                    <el-option value="SOLUSDT" label="SOLUSDT" />
                    <el-option value="ADAUSDT" label="ADAUSDT" />
                  </el-select>
                </div>
                
                <div class="form-group">
                  <label for="interval">周期</label>
                  <el-select
                    v-model="collectionForm.interval"
                    multiple
                    clearable
                    placeholder="请选择周期"
                    class="form-control"
                  >
                    <el-option value="1m" label="1分钟" />
                    <el-option value="5m" label="5分钟" />
                    <el-option value="15m" label="15分钟" />
                    <el-option value="30m" label="30分钟" />
                    <el-option value="1h" label="1小时" />
                    <el-option value="4h" label="4小时" />
                    <el-option value="1d" label="1天" />
                  </el-select>
                </div>
              </div>
              
              <!-- 第二行：开始时间和结束时间 -->
              <div class="form-row">
                <div class="form-group">
                  <label for="start">开始时间</label>
                  <el-date-picker
                    v-model="collectionForm.start"
                    type="datetime"
                    placeholder="请选择开始时间"
                    format="YYYY-MM-DD HH:mm:ss"
                    value-format="YYYY-MM-DD HH:mm:ss"
                    class="form-control"
                    style="width: 100%"
                  />
                </div>
                
                <div class="form-group">
                  <label for="end">结束时间</label>
                  <el-date-picker
                    v-model="collectionForm.end"
                    type="datetime"
                    placeholder="请选择结束时间"
                    format="YYYY-MM-DD HH:mm:ss"
                    value-format="YYYY-MM-DD HH:mm:ss"
                    class="form-control"
                    style="width: 100%"
                  />
                </div>
              </div>
              
              <!-- 第三行：来源和蜡烛图类型 -->
              <div class="form-row">
                <div class="form-group">
                  <label for="exchange">来源</label>
                  <el-select
                    v-model="collectionForm.exchange"
                    placeholder="请选择来源"
                    class="form-control"
                  >
                    <el-option
                      v-for="option in exchangeOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </div>
                
                <div class="form-group">
                  <label for="candle_type">蜡烛图类型</label>
                  <el-select
                    v-model="collectionForm.candle_type"
                    placeholder="请选择蜡烛图类型"
                    class="form-control"
                  >
                    <el-option
                      v-for="option in candleTypeOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </div>
              </div>
              
              <!-- 第三行：最大工作线程数 -->
              <div class="form-row">
                <div class="form-group">
                  <label for="max_workers">最大工作线程数</label>
                  <el-input-number
                    v-model="collectionForm.max_workers"
                    :min="1"
                    :max="10"
                    :step="1"
                    placeholder="请输入最大工作线程数"
                    class="form-control"
                  />
                </div>
              </div>
              
              <!-- 操作按钮 -->
              <div class="data-actions">
                <button class="btn btn-primary" @click="loadData" :disabled="isTaskRunning">开始下载</button>
                <button class="btn btn-secondary" @click="refreshCollectionData">刷新数据</button>
              </div>
            </div>
          </div>
          
          <!-- 任务管理 -->
          <div class="data-section">
            <h3>任务管理</h3>
            
            <!-- 当前任务状态 -->
            <div v-if="currentTaskId" class="current-task-section">
              <h4>当前任务</h4>
              <div class="task-info">
                <div class="task-id">
                  <span class="label">任务ID:</span>
                  <span class="value">{{ currentTaskId }}</span>
                </div>
                <div class="task-status">
                  <span class="label">状态:</span>
                  <span class="value" :class="`status-${taskStatus}`">{{ getStatusText(taskStatus) }}</span>
                </div>
              </div>
              
              <!-- 任务详细信息 -->
              <div class="task-details-info">
                <div class="detail-item">
                  <span class="label">任务类型:</span>
                  <span class="value">下载加密货币数据</span>
                </div>
                <div class="detail-item">
                  <span class="label">创建时间:</span>
                  <span class="value">{{ new Date().toLocaleString() }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">品种:</span>
                  <span class="value">{{ collectionForm.symbols.join(', ') || '未指定' }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">周期:</span>
                  <span class="value">{{ collectionForm.interval.join(', ') || '未指定' }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">时间范围:</span>
                  <span class="value">{{ collectionForm.start }} 至 {{ collectionForm.end }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">来源:</span>
                  <span class="value">{{ collectionForm.exchange }}</span>
                </div>
              </div>
              
              <!-- 任务进度条 -->
              <div class="task-progress">
                <div class="progress-bar-container">
                  <div class="progress-bar" :style="{ width: `${taskProgress}%` }"></div>
                </div>
                <div class="progress-text">{{ taskProgress }}%</div>
              </div>
            </div>
            
            <!-- 最近任务列表 -->
            <div class="recent-tasks-section">
              <h4>最近任务</h4>
              <div v-if="isLoading" class="loading-state">
                <div class="loading-spinner"></div>
                <span>加载任务列表中...</span>
              </div>
              <div v-else-if="tasks.length === 0" class="empty-state">
                <span>暂无任务记录</span>
              </div>
              <div v-else class="recent-tasks-container">
                <div v-for="task in tasks" :key="task.task_id" class="task-card">
                  <div class="task-details">
                    <div class="task-params-info">
                      <div class="param-item">
                        <span class="label">品种:</span>
                        <el-tooltip
                          :content="Array.isArray(task.params?.symbols) ? task.params.symbols.join(', ') : task.params?.symbols || '未指定'"
                          placement="top"
                          effect="dark"
                        >
                          <span class="value">{{ Array.isArray(task.params?.symbols) ? task.params.symbols.join(', ') : task.params?.symbols || '未指定' }}</span>
                        </el-tooltip>
                      </div>
                      <div class="param-item">
                        <span class="label">周期:</span>
                        <span class="value">{{ task.params?.interval || '未指定' }}</span>
                      </div>
                      <div class="param-item">
                        <span class="label">来源:</span>
                        <span class="value">{{ task.params?.exchange || '未指定' }}</span>
                      </div>
                      <div class="param-item">
                        <span class="label">时间范围:</span>
                        <span class="value">{{ task.params?.start || '未指定' }} 至 {{ task.params?.end || '未指定' }}</span>
                      </div>
                    </div>
                    <div class="task-time-info">
                      <div class="time-item">
                        <span class="label">创建时间:</span>
                        <span class="value">{{ new Date(task.created_at).toLocaleString() }}</span>
                      </div>
                      <div v-if="task.completed_at" class="time-item">
                        <span class="label">完成时间:</span>
                        <span class="value">{{ new Date(task.completed_at).toLocaleString() }}</span>
                      </div>
                    </div>
                    <div class="task-progress-info">
                      <span class="label">进度:</span>
                      <div class="progress-bar-container">
                        <div class="progress-bar" :style="{ width: `${task.progress?.percentage || 0}%` }"></div>
                      </div>
                      <span class="progress-value">{{ task.progress?.percentage || 0 }}%</span>
                    </div>
                  </div>
                  <div class="task-header">
                    <div class="task-id-info">
                      <span class="label">任务ID:</span>
                      <span class="value">{{ task.task_id }}</span>
                    </div>
                    <div class="task-status-badge" :class="`status-${task.status}`">
                      {{ getStatusText(task.status) }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 数据目录概览 -->
          <div class="data-section" v-if="dataInfo">
            <h3>数据目录概览</h3>
            <div class="directory-overview">
              <div class="overview-item">
                <span class="overview-label">交易日历:</span>
                <span class="overview-value">{{ calendarCount }}</span>
              </div>
              <div class="overview-item">
                <span class="overview-label">股票数量:</span>
                <span class="overview-value">{{ stockCount }}</span>
              </div>
              <div class="overview-item">
                <span class="overview-label">特征数据:</span>
                <span class="overview-value">{{ featureCount }}</span>
              </div>
              <div class="overview-item">
                <span class="overview-label">数据状态:</span>
                <span class="overview-value" :class="{ 'result-success': dataStatus.data_loaded, 'result-error': !dataStatus.data_loaded }">
                  {{ dataStatus.data_loaded ? '已加载' : '未加载' }}
                </span>
              </div>
            </div>
          </div>
          
          <!-- 交易日历列表 -->
          <div class="data-section" v-if="calendars.length > 0">
            <h3>交易日历</h3>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>频率</th>
                    <th>日期数量</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="calendar in calendars" :key="calendar.freq">
                    <td>{{ calendar.freq }}</td>
                    <td>{{ calendar.count }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          
          <!-- 股票列表 -->
          <div class="data-section" v-if="instruments.length > 0">
            <h3>股票列表</h3>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>指数名称</th>
                    <th>股票数量</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="instrument in instruments" :key="instrument.index_name">
                    <td>{{ instrument.index_name }}</td>
                    <td>{{ instrument.count }}</td>
                    <td>
                      <button class="btn btn-sm btn-secondary" @click="viewSymbols(instrument.index_name)">查看股票</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            
            <!-- 股票详情弹窗 -->
            <div v-if="showSymbolsModal" class="modal-overlay" @click="showSymbolsModal = false">
              <div class="modal-content" @click.stop>
                <div class="modal-header">
                  <h3>{{ selectedIndex }} 股票列表</h3>
                  <button class="modal-close" @click="showSymbolsModal = false">&times;</button>
                </div>
                <div class="modal-body">
                  <div class="symbol-list">
                    <div v-for="symbol in selectedSymbols" :key="symbol" class="symbol-item">{{ symbol }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 特征数据列表 -->
          <div class="data-section" v-if="features.length > 0">
            <h3>特征数据</h3>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>股票代码</th>
                    <th>特征数量</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="feature in features" :key="feature.symbol">
                    <td>{{ feature.symbol }}</td>
                    <td>{{ feature.count }}</td>
                    <td>
                      <button class="btn btn-sm btn-secondary" @click="viewSymbolFeatures(feature.symbol)">查看特征</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            
            <!-- 特征详情弹窗 -->
            <div v-if="showFeaturesModal" class="modal-overlay" @click="showFeaturesModal = false">
              <div class="modal-content" @click.stop>
                <div class="modal-header">
                  <h3>{{ selectedSymbol }} 特征列表</h3>
                  <button class="modal-close" @click="showFeaturesModal = false">&times;</button>
                </div>
                <div class="modal-body">
                  <div class="feature-list">
                    <div v-for="feature in selectedFeatures" :key="feature" class="feature-item">{{ feature }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- 操作成功提示 -->
    <div v-if="showSuccessMessage" class="success-message">
      {{ successMessage }}
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, reactive, ref, onMounted } from 'vue'
import axios from 'axios'
/* @ts-ignore */
import AssetPoolManager from '../components/AssetPoolManager.vue'

/**
 * 菜单项类型定义
 */
interface MenuItem {
  id: string
  title: string
  icon: string
}

/**
 * 加密货币数据类型定义
 */
interface CryptoCurrency {
  id: string
  name: string
  symbol: string
  currentPrice: number
  priceChange24h: number
  marketCap: number
  tradingVolume: number
}

/**
 * 股票数据类型定义
 */
interface Stock {
  symbol: string
  companyName: string
  currentPrice: number
  priceChange: number
  priceChangePercent: number
  openPrice: number
  highPrice: number
  lowPrice: number
}

/**
 * 数据管理页面组件
 * 功能：展示和管理加密货币与股票数据
 */
export default defineComponent({
  name: 'DataManagement',
  components: {
    AssetPoolManager
  },
  setup() {
    // 当前选中的标签页
    const currentTab = ref<string>('crypto')
    
    // 显示成功消息标志
    const showSuccessMessage = ref<boolean>(false)
    
    // 成功消息内容
    const successMessage = ref<string>('')
    
    // 菜单项列表
    const menuItems: MenuItem[] = [
      { id: 'crypto', title: '加密货币', icon: 'icon-crypto' },
      { id: 'stock', title: '股票', icon: 'icon-stock' },
      { id: 'import', title: '数据导入', icon: 'icon-import' },
      { id: 'collection', title: 'crypto数据采集', icon: 'icon-collection' },
      { id: 'quality', title: '数据质量', icon: 'icon-quality' },
      { id: 'visualization', title: '数据可视化', icon: 'icon-visualization' },
      { id: 'asset-pools', title: '资产池管理', icon: 'icon-asset-pool' }
    ]
    
    // 加密货币数据
    const cryptoData = reactive<CryptoCurrency[]>([
      {
        id: 'bitcoin',
        name: '比特币',
        symbol: 'BTC',
        currentPrice: 42567.89,
        priceChange24h: 2.56,
        marketCap: 815245678901,
        tradingVolume: 35678901234
      },
      {
        id: 'ethereum',
        name: '以太坊',
        symbol: 'ETH',
        currentPrice: 2245.67,
        priceChange24h: -1.23,
        marketCap: 268901234567,
        tradingVolume: 18901234567
      },
      {
        id: 'binancecoin',
        name: '币安币',
        symbol: 'BNB',
        currentPrice: 345.67,
        priceChange24h: 0.89,
        marketCap: 56789012345,
        tradingVolume: 4567890123
      },
      {
        id: 'cardano',
        name: '卡尔达诺',
        symbol: 'ADA',
        currentPrice: 1.23,
        priceChange24h: 5.67,
        marketCap: 41234567890,
        tradingVolume: 3234567890
      },
      {
        id: 'solana',
        name: '索拉纳',
        symbol: 'SOL',
        currentPrice: 102.34,
        priceChange24h: -2.34,
        marketCap: 34567890123,
        tradingVolume: 2890123456
      }
    ])
    
    // 股票数据
    const stockData = reactive<Stock[]>([
      {
        symbol: 'AAPL',
        companyName: '苹果公司',
        currentPrice: 187.45,
        priceChange: 2.34,
        priceChangePercent: 1.26,
        openPrice: 185.23,
        highPrice: 188.76,
        lowPrice: 184.98
      },
      {
        symbol: 'MSFT',
        companyName: '微软公司',
        currentPrice: 401.23,
        priceChange: -3.45,
        priceChangePercent: -0.85,
        openPrice: 404.68,
        highPrice: 405.12,
        lowPrice: 399.87
      },
      {
        symbol: 'GOOGL',
        companyName: 'Alphabet公司',
        currentPrice: 176.89,
        priceChange: 1.23,
        priceChangePercent: 0.70,
        openPrice: 175.66,
        highPrice: 177.45,
        lowPrice: 175.23
      },
      {
        symbol: 'AMZN',
        companyName: '亚马逊公司',
        currentPrice: 178.45,
        priceChange: -0.56,
        priceChangePercent: -0.31,
        openPrice: 179.01,
        highPrice: 180.23,
        lowPrice: 178.12
      },
      {
        symbol: 'TSLA',
        companyName: '特斯拉公司',
        currentPrice: 176.32,
        priceChange: 5.67,
        priceChangePercent: 3.31,
        openPrice: 170.65,
        highPrice: 177.89,
        lowPrice: 169.98
      }
    ])
    
    // 导入表单数据
    interface ImportForm {
      dataType: string
      exchange: string
      startDate: string
      endDate: string
      interval: string
      symbols: string
    }
    
    const importForm = reactive<ImportForm>({
      dataType: 'crypto',
      exchange: 'binance',
      startDate: '',
      endDate: '',
      interval: '1d',
      symbols: ''
    })
    
    // 导入进度和日志
    const importProgress = ref<number>(0)
    const importLog = ref<string[]>([])
    
    // 数据质量检查表单数据
    interface QualityForm {
      dataType: string
      symbol: string
      startDate: string
      endDate: string
    }
    
    const qualityForm = reactive<QualityForm>({
      dataType: 'crypto',
      symbol: '',
      startDate: '',
      endDate: ''
    })
    
    // 数据质量检查结果
    interface QualityResult {
      totalRows: number
      missingValues: number
      outliers: number
      completeness: number
      details: string
    }
    
    const qualityResult = ref<QualityResult | null>(null)
    
    // 数据可视化表单数据
    interface VizForm {
      dataType: string
      symbol: string
      startDate: string
      endDate: string
      chartType: string
      indicator: string
    }
    
    const vizForm = reactive<VizForm>({
      dataType: 'crypto',
      symbol: '',
      startDate: '',
      endDate: '',
      chartType: 'candlestick',
      indicator: 'close'
    })
    
    // 可视化图表URL
    const vizChartUrl = ref<string>('')
    
    /**
     * 格式化大数字
     * @param num 要格式化的数字
     * @returns 格式化后的字符串
     */
    const formatNumber = (num: number): string => {
      if (num >= 1000000000) {
        return (num / 1000000000).toFixed(2) + 'B'
      } else if (num >= 1000000) {
        return (num / 1000000).toFixed(2) + 'M'
      } else if (num >= 1000) {
        return (num / 1000).toFixed(2) + 'K'
      }
      return num.toString()
    }
    
    /**
     * 刷新加密货币数据
     */
    const refreshCryptoData = (): void => {
      // 模拟刷新数据操作
      showMessage('加密货币数据已刷新')
      console.log('刷新加密货币数据')
    }
    
    /**
     * 导出加密货币数据
     */
    const exportCryptoData = (): void => {
      // 模拟导出数据操作
      showMessage('加密货币数据已导出')
      console.log('导出加密货币数据')
    }
    
    /**
     * 刷新股票数据
     */
    const refreshStockData = (): void => {
      // 模拟刷新数据操作
      showMessage('股票数据已刷新')
      console.log('刷新股票数据')
    }
    
    /**
     * 导出股票数据
     */
    const exportStockData = (): void => {
      // 模拟导出数据操作
      showMessage('股票数据已导出')
      console.log('导出股票数据')
    }
    
    /**
     * 显示操作成功消息
     * @param message 要显示的消息内容
     */
    const showMessage = (message: string): void => {
      successMessage.value = message
      showSuccessMessage.value = true
      // 3秒后隐藏成功提示
      setTimeout(() => {
        showSuccessMessage.value = false
      }, 3000)
    }
    
    /**
     * 处理文件上传
     * @param event 文件上传事件
     */
    const handleFileUpload = (event: Event): void => {
      const target = event.target as HTMLInputElement
      if (target.files) {
        const files = Array.from(target.files)
        importLog.value.push(`已选择 ${files.length} 个文件`)
        files.forEach(file => {
          importLog.value.push(`- ${file.name}`)
        })
      }
    }
    
    /**
     * 开始导入数据
     */
    const startImport = (): void => {
      importProgress.value = 0
      importLog.value = ['开始导入数据...']
      
      // 模拟导入过程
      const interval = setInterval(() => {
        importProgress.value += 10
        if (importProgress.value <= 100) {
          importLog.value.push(`导入进度: ${importProgress.value}%`)
        } else {
          clearInterval(interval)
          importProgress.value = 100
          importLog.value.push('数据导入完成！')
          showMessage('数据导入成功')
        }
      }, 500)
    }
    
    /**
     * 重置导入表单
     */
    const resetImportForm = (): void => {
      importForm.dataType = 'crypto'
      importForm.exchange = 'binance'
      importForm.startDate = ''
      importForm.endDate = ''
      importForm.interval = '1d'
      importForm.symbols = ''
      importProgress.value = 0
      importLog.value = []
    }
    
    /**
     * 开始数据质量检查
     */
    const startQualityCheck = (): void => {
      importLog.value = ['开始数据质量检查...']
      
      // 模拟数据质量检查结果
      setTimeout(() => {
        qualityResult.value = {
          totalRows: 1000,
          missingValues: 15,
          outliers: 8,
          completeness: 97.7,
          details: `<h4>详细报告</h4><p>数据总量: 1000 条</p><p>缺失值: 15 条 (1.5%)</p><p>异常值: 8 条 (0.8%)</p><p>数据完整性: 97.7%</p><h5>缺失值详情</h5><p>- 收盘价: 5 条</p><p>- 成交量: 10 条</p><h5>异常值详情</h5><p>- 价格异常: 3 条</p><p>- 成交量异常: 5 条</p>`
        }
        importLog.value.push('数据质量检查完成！')
        showMessage('数据质量检查完成')
      }, 1500)
    }
    
    /**
     * 根据完整性值返回结果类名
     * @param completeness 数据完整性百分比
     * @returns 结果类名
     */
    const resultClass = (completeness: number): string => {
      if (completeness >= 95) {
        return 'result-success'
      } else if (completeness >= 80) {
        return 'result-warning'
      } else {
        return 'result-error'
      }
    }
    
    /**
     * 生成数据可视化图表
     */
    const generateVisualization = (): void => {
      importLog.value = ['开始生成可视化图表...']
      
      // 模拟生成图表
      setTimeout(() => {
        // 这里应该是实际的图表生成逻辑，现在使用占位图
        vizChartUrl.value = 'https://via.placeholder.com/800x400?text=数据可视化图表'
        importLog.value.push('图表生成完成！')
        showMessage('图表生成成功')
      }, 1000)
    }
    
    /**
     * 导出图表
     */
    const exportChart = (): void => {
      if (vizChartUrl.value) {
        // 模拟导出图表
        importLog.value.push('开始导出图表...')
        setTimeout(() => {
          importLog.value.push('图表导出完成！')
          showMessage('图表导出成功')
        }, 500)
      } else {
        showMessage('请先生成图表')
      }
    }
    
    // 数据采集相关
    const collectionForm = reactive({
      symbols: [] as string[], // 品种，支持多选
      interval: [] as string[], // 周期，支持多选
      start: '' as string, // 开始时间
      end: '' as string, // 结束时间
      exchange: 'binance' as string, // 来源，默认'binance'
      max_workers: 1 as number, // 最大工作线程数，默认1
      candle_type: 'spot' as string // 蜡烛图类型，默认'spot'
    })
    
    // 选项数据
    const exchangeOptions = ref([
      { value: 'binance', label: 'Binance' },
      { value: 'okx', label: 'OKX' }
    ])
    
    const candleTypeOptions = ref([
      { value: 'spot', label: '现货' },
      { value: 'futures', label: '期货' },
      { value: 'option', label: '期权' }
    ])
    
    const dataInfo = ref<any>(null)
    const dataStatus = ref<any>({ data_loaded: false, qlib_dir: '' })
    const calendars = ref<any[]>([])
    const instruments = ref<any[]>([])
    const features = ref<any[]>([])
    const calendarCount = ref(0)
    const stockCount = ref(0)
    const featureCount = ref(0)
    
    // 任务列表相关
    const tasks = ref<any[]>([])
    const taskFilters = reactive({
      status: '' as string,
      task_type: 'download_crypto' as string // 只获取download_crypto类型的任务
    })
    const isLoading = ref(false)
    
    // 页面加载时获取任务列表
    onMounted(() => {
      console.log('页面加载，调用getTasks')
      getTasks()
    })
    
    // 弹窗相关
    const showSymbolsModal = ref(false)
    const showFeaturesModal = ref(false)
    const selectedIndex = ref('')
    const selectedSymbols = ref<string[]>([])
    const selectedSymbol = ref('')
    const selectedFeatures = ref<string[]>([])
    
    // 任务状态管理
    const currentTaskId = ref<string>('') // 当前任务ID
    const taskStatus = ref<string>('') // 任务状态
    const taskProgress = ref<number>(0) // 任务进度
    const taskLog = ref<string[]>([]) // 任务日志
    const isTaskRunning = ref<boolean>(false) // 任务是否正在运行
    let taskInterval: number | null = null // 任务状态查询定时器
    
    /**
     * 查询任务状态
     */
    const queryTaskStatus = async () => {
      if (!currentTaskId.value) return
      
      try {
        // 使用相对路径，通过Vite代理发送请求
        const response = await axios.get(`/api/data/task/${currentTaskId.value}`)
        
        if (response.data.code === 0) {
          const taskData = response.data.data
          
          // 更新任务状态
          taskStatus.value = taskData.status || 'unknown'
          
          // 更新任务进度
          let progressValue = 0
          if (taskData.progress && typeof taskData.progress === 'object') {
            // 如果progress是对象，使用percentage字段
            progressValue = taskData.progress.percentage || 0
          } else {
            // 否则直接使用progress值
            progressValue = taskData.progress || 0
          }
          taskProgress.value = progressValue
          
          // 更新任务日志
          taskLog.value = Array.isArray(taskData.log) ? taskData.log : []
          
          // 如果任务完成、失败、取消或进度达到100%，停止定时查询
          if (taskStatus.value === 'completed' || taskStatus.value === 'failed' || taskStatus.value === 'canceled' || progressValue >= 100) {
            isTaskRunning.value = false
            if (taskInterval) {
              clearInterval(taskInterval)
              taskInterval = null
            }
            showMessage(`任务${taskStatus.value === 'completed' ? '完成' : taskStatus.value === 'failed' ? '失败' : taskStatus.value === 'canceled' ? '已取消' : '完成'}`)
          }
        }
      } catch (error) {
        console.error('查询任务状态失败:', error)
        // 后端报错，停止轮询
        isTaskRunning.value = false
        if (taskInterval) {
          clearInterval(taskInterval)
          taskInterval = null
        }
        showMessage('查询任务状态失败，请检查后端服务是否正常')
      }
    }
    
    /**
     * 获取任务列表
     */
    const getTasks = async () => {
      isLoading.value = true
      try {
        console.log('开始获取任务列表，参数:', {
          page: 1,
          page_size: 10,
          sort_by: 'created_at',
          sort_order: 'desc',
          ...taskFilters
        })
        
        const response = await axios.get('/api/data/tasks', {
          params: {
            page: 1,
            page_size: 5,
            sort_by: 'created_at',
            sort_order: 'desc',
            ...taskFilters
          }
        })
        
        console.log('获取任务列表响应:', response.data)
        
        // 检查响应结构
        if (response.data && response.data.code === 0) {
          if (response.data.data && Array.isArray(response.data.data.tasks)) {
            tasks.value = response.data.data.tasks
            console.log('处理后的任务列表:', tasks.value)
            console.log('任务数量:', tasks.value.length)
          } else {
            console.error('响应数据结构异常，tasks不是数组:', response.data.data)
            tasks.value = []
          }
        } else {
          console.error('获取任务列表失败，响应代码:', response.data.code, '消息:', response.data.message)
          showMessage(`获取任务列表失败: ${response.data.message || '未知错误'}`)
          tasks.value = []
        }
      } catch (error: any) {
        console.error('获取任务列表异常:', error.message || error)
        console.error('错误详情:', error)
        showMessage('获取任务列表失败，请检查网络连接或后端服务')
        tasks.value = []
      } finally {
        isLoading.value = false
      }
    }
    
    /**
     * 获取任务状态类型
     */
    const getStatusType = (status: string) => {
      switch (status) {
        case 'running':
          return 'warning'
        case 'completed':
          return 'success'
        case 'failed':
          return 'danger'
        case 'pending':
          return 'info'
        default:
          return 'info'
      }
    }
    
    /**
     * 获取任务状态文本
     */
    const getStatusText = (status: string) => {
      switch (status) {
        case 'running':
          return '运行中'
        case 'completed':
          return '已完成'
        case 'failed':
          return '失败'
        case 'pending':
          return '等待中'
        default:
          return status
      }
    }
    
    /**
     * 下载加密货币数据
     */
    const loadData = async () => {
      try {
        // 使用相对路径，通过Vite代理发送请求
        const response = await axios.post('/api/data/download/crypto', {
          ...collectionForm
        })
        
        if (response.data.code === 0) {
          // 保存返回的task_id
          currentTaskId.value = response.data.data.task_id
          isTaskRunning.value = true
          taskStatus.value = 'running'
          taskProgress.value = 0
          taskLog.value = []
          
          // 开始定时查询任务状态，每1秒查询一次
          if (taskInterval) {
            clearInterval(taskInterval)
          }
          taskInterval = window.setInterval(queryTaskStatus, 1000)
          
          // 立即查询一次任务状态
          await queryTaskStatus()
        } else {
          showMessage(`数据下载失败: ${response.data.message}`)
        }
      } catch (error) {
        console.error('数据下载失败:', error)
        showMessage('数据下载失败，请检查后端服务是否正常')
      }
    }
    
    /**
     * 刷新数据采集页面数据
     */
    const refreshCollectionData = async () => {
      try {
        // 获取数据服务状态
        // 使用相对路径，通过Vite代理发送请求
        const statusResponse = await axios.get('/api/data/status')
        if (statusResponse.data.code === 0) {
          dataStatus.value = statusResponse.data.data
        }
        
        // 如果数据已加载，获取详细数据信息
        if (dataStatus.value.data_loaded) {
          // 获取数据信息
          const infoResponse = await axios.get('/api/data/info')
          if (infoResponse.data.code === 0) {
            dataInfo.value = infoResponse.data.data
          }
          
          // 获取交易日历
          const calendarsResponse = await axios.get('/api/data/calendars')
          if (calendarsResponse.data.code === 0) {
            calendars.value = calendarsResponse.data.data
            calendarCount.value = calendars.value.length
          }
          
          // 获取成分股
          const instrumentsResponse = await axios.get('/api/data/instruments')
          if (instrumentsResponse.data.code === 0) {
            instruments.value = instrumentsResponse.data.data
            stockCount.value = instruments.value.reduce((sum: number, item: any) => sum + item.count, 0)
          }
          
          // 获取特征数据
          const featuresResponse = await axios.get('/api/data/features')
          if (featuresResponse.data.code === 0) {
            features.value = featuresResponse.data.data
            featureCount.value = features.value.length
          }
        }
        
        // 刷新任务列表
        console.log('刷新数据，调用getTasks')
        await getTasks()
      } catch (error) {
        console.error('刷新数据失败:', error)
        showMessage('刷新数据失败，请检查后端服务是否正常')
      }
    }
    
    /**
     * 查看股票列表
     */
    const viewSymbols = async (indexName: string) => {
      try {
        // 使用相对路径，通过Vite代理发送请求
        const response = await axios.get(`/api/data/instruments?index_name=${indexName}`)
        if (response.data.code === 0) {
          selectedIndex.value = indexName
          selectedSymbols.value = response.data.data.symbols
          showSymbolsModal.value = true
        }
      } catch (error) {
        console.error('获取股票列表失败:', error)
        showMessage('获取股票列表失败')
      }
    }
    
    /**
     * 查看股票特征
     */
    const viewSymbolFeatures = async (symbol: string) => {
      try {
        // 使用相对路径，通过Vite代理发送请求
        const response = await axios.get(`/api/data/features/${symbol}`)
        if (response.data.code === 0) {
          selectedSymbol.value = symbol
          selectedFeatures.value = response.data.data.features
          showFeaturesModal.value = true
        }
      } catch (error) {
        console.error('获取股票特征失败:', error)
        showMessage('获取股票特征失败')
      }
    }
    
    // 页面加载时获取任务列表
    onMounted(() => {
      getTasks()
    })
    
    return {
        currentTab,
        showSuccessMessage,
        successMessage,
        menuItems,
        cryptoData,
        stockData,
        formatNumber,
        refreshCryptoData,
        exportCryptoData,
        refreshStockData,
        exportStockData,
        // 数据导入相关
        importForm,
        importProgress,
        importLog,
        handleFileUpload,
        startImport,
        resetImportForm,
        // 数据质量检查相关
        qualityForm,
        qualityResult,
        startQualityCheck,
        resultClass,
        // 数据可视化相关
        vizForm,
        vizChartUrl,
        generateVisualization,
        exportChart,
        // 数据采集相关
        collectionForm,
        dataInfo,
        dataStatus,
        calendars,
        instruments,
        features,
        calendarCount,
        stockCount,
        featureCount,
        loadData,
        refreshCollectionData,
        // 选项数据
        exchangeOptions,
        candleTypeOptions,
        // 任务状态相关
        currentTaskId,
        taskStatus,
        taskProgress,
        taskLog,
        isTaskRunning,
        // 任务列表相关
        tasks,
        isLoading,
        getTasks,
        getStatusType,
        getStatusText,
        // 弹窗相关
        showSymbolsModal,
        showFeaturesModal,
        selectedIndex,
        selectedSymbols,
        selectedSymbol,
        selectedFeatures,
        viewSymbols,
        viewSymbolFeatures
    }
  }
})
</script>

<style scoped>
.data-management-container {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 30px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.page-header h1 {
  margin: 0;
  font-size: 28px;
  color: #333;
}

.data-management-content {
  display: flex;
  flex-direction: column;
  gap: 30px;
  min-height: 600px;
}

.data-management-sidebar {
  width: 100%;
  flex-shrink: 0;
}

.data-management-nav ul {
  list-style: none;
  padding: 0;
  margin: 0;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border: 1px solid #e0e0e0;
  display: flex;
  overflow-x: auto;
}

.data-management-nav li {
  display: flex;
  align-items: center;
  padding: 15px 20px;
  cursor: pointer;
  transition: background-color 0.3s;
  color: #666;
  font-size: 14px;
}

.data-management-nav li:hover {
  background-color: #f8f9fa;
}

.data-management-nav li.active {
  background-color: #4a6cf7;
  color: white;
  font-weight: 500;
}

.data-management-nav li i {
  margin-right: 12px;
  font-size: 16px;
}

/* 模拟图标 */
.icon-crypto::before { content: '₿'; }
.icon-stock::before { content: '📈'; }

.data-management-main {
  flex: 1;
  background: white;
  border-radius: 8px;
  padding: 30px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border: 1px solid #e0e0e0;
}

.data-panel h2 {
  margin-top: 0;
  margin-bottom: 30px;
  font-size: 24px;
  color: #333;
}

.data-section {
  margin-bottom: 40px;
}

.data-actions {
  display: flex;
  gap: 15px;
  margin-bottom: 20px;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.3s;
}

.btn-primary {
  background-color: #4a6cf7;
  color: white;
}

.btn-primary:hover {
  background-color: #3a5ad9;
}

.btn-secondary {
  background-color: #e0e0e0;
  color: #333;
}

.btn-secondary:hover {
  background-color: #d0d0d0;
}

.data-table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  background-color: #f8f9fa;
  padding: 12px 15px;
  text-align: left;
  font-weight: 500;
  color: #333;
  border-bottom: 2px solid #e0e0e0;
}

.data-table td {
  padding: 12px 15px;
  border-bottom: 1px solid #f0f0f0;
  color: #555;
}

.data-table tr:hover {
  background-color: #f8f9fa;
}

.price-up {
  color: #2ed573;
  font-weight: 500;
}

.price-down {
  color: #ff6348;
  font-weight: 500;
}

/* 成功提示 */
.success-message {
  position: fixed;
  top: 20px;
  right: 20px;
  background-color: #2ed573;
  color: white;
  padding: 15px 25px;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

/* 表单样式 */
.form-row {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #333;
  font-size: 14px;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.3s;
}

.form-control:focus {
  outline: none;
  border-color: #4a6cf7;
  box-shadow: 0 0 0 2px rgba(74, 108, 247, 0.1);
}

.form-control-file {
  width: 100%;
  padding: 8px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  background-color: #f8f9fa;
  cursor: pointer;
}

/* 导入表单样式 */
.import-form {
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
  border: 1px solid #e0e0e0;
}

/* 导入进度样式 */
.import-progress {
  margin: 20px 0;
  display: flex;
  align-items: center;
  gap: 15px;
}

.progress-bar-container {
  flex: 1;
  height: 10px;
  background-color: #e0e0e0;
  border-radius: 5px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background-color: #4a6cf7;
  transition: width 0.3s ease;
}

.progress-text {
  font-weight: 500;
  color: #4a6cf7;
  min-width: 50px;
}

/* 导入日志样式 */
.import-log {
  margin-top: 20px;
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  max-height: 300px;
  overflow-y: auto;
}

.import-log h3 {
  margin-top: 0;
  margin-bottom: 15px;
  font-size: 16px;
  color: #333;
}

.log-content {
  font-family: monospace;
  font-size: 14px;
}

.log-item {
  margin-bottom: 8px;
  color: #666;
}

/* 数据质量检查样式 */
.quality-check-form {
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
  border: 1px solid #e0e0e0;
}

.quality-result {
  margin-top: 20px;
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.quality-result h3 {
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 18px;
  color: #333;
}

.result-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.result-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  background-color: white;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.result-label {
  font-weight: 500;
  color: #666;
}

.result-value {
  font-weight: 600;
  font-size: 18px;
}

.result-success {
  color: #2ed573;
}

.result-warning {
  color: #ffa502;
}

.result-error {
  color: #ff6348;
}

.quality-details {
  margin-top: 20px;
}

.quality-details h4 {
  margin-top: 0;
  margin-bottom: 15px;
  font-size: 16px;
  color: #333;
}

.details-content {
  background-color: white;
  padding: 15px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  line-height: 1.6;
}

/* 数据可视化样式 */
.visualization-form {
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
  border: 1px solid #e0e0e0;
}

.visualization-container {
  margin-top: 20px;
  background-color: white;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  text-align: center;
}

.chart-container {
  margin: 0 auto;
  max-width: 100%;
}

.chart-image {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.chart-placeholder {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 400px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px dashed #e0e0e0;
}

.placeholder-content {
  text-align: center;
  color: #999;
}

.placeholder-content i {
  font-size: 48px;
  margin-bottom: 15px;
  display: block;
}

/* 图标样式 */
.icon-import::before { content: '📥'; }
.icon-quality::before { content: '🔍'; }
.icon-visualization::before { content: '📊'; }
.icon-chart::before { content: '📈'; }
.icon-collection::before { content: '📥'; }

/* 任务状态样式 */
.task-status-section {
  margin-top: 30px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.task-status-section h4 {
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 18px;
  color: #333;
}

.task-info {
  display: flex;
  gap: 30px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.task-id, .task-status {
  display: flex;
  align-items: center;
}

.task-id .label, .task-status .label {
  font-weight: 500;
  color: #666;
  margin-right: 10px;
}

.task-id .value {
  font-family: monospace;
  color: #4a6cf7;
}

.task-status .value {
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 14px;
}

.status-running {
  background-color: #e3f2fd;
  color: #1976d2;
}

.status-completed {
  background-color: #e8f5e8;
  color: #388e3c;
}

.status-failed {
  background-color: #ffebee;
  color: #d32f2f;
}

.status-canceled {
  background-color: #fff3e0;
  color: #f57c00;
}

.task-progress {
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 15px;
}

.progress-bar-container {
  flex: 1;
  height: 10px;
  background-color: #e0e0e0;
  border-radius: 5px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background-color: #4a6cf7;
  transition: width 0.3s ease;
}

.progress-text {
  font-weight: 500;
  color: #4a6cf7;
  min-width: 50px;
}

.task-log {
  margin-top: 20px;
}

.task-log h5 {
  margin-top: 0;
  margin-bottom: 15px;
  font-size: 16px;
  color: #333;
}

.log-content {
  background-color: white;
  padding: 15px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  max-height: 300px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 14px;
}

.log-item {
  margin-bottom: 8px;
  color: #666;
  line-height: 1.5;
}

.log-item.empty {
  color: #999;
  font-style: italic;
}

/* 数据采集样式 */
.directory-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.overview-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  background-color: white;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.overview-label {
  font-weight: 500;
  color: #666;
}

.overview-value {
  font-weight: 600;
  font-size: 18px;
  color: #4a6cf7;
}

/* 弹窗样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.symbol-list, .feature-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.symbol-item, .feature-item {
  padding: 10px;
  background-color: #f8f9fa;
  border-radius: 4px;
  text-align: center;
  font-size: 14px;
}

/* 任务管理样式 */
.current-task-section {
  margin-bottom: 30px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.recent-tasks-section {
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.current-task-section h4,
.recent-tasks-section h4 {
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 16px;
  color: #333;
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 10px;
}

/* 任务详细信息样式 */
.task-details-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 15px;
  margin: 20px 0;
  padding: 20px;
  background-color: white;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-item .label {
  font-weight: 500;
  color: #666;
  font-size: 14px;
  min-width: 80px;
}

.detail-item .value {
  color: #333;
  font-size: 14px;
  word-break: break-all;
}

/* 任务列表样式 */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
  color: #666;
  gap: 10px;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #e0e0e0;
  border-top: 2px solid #4a6cf7;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
  color: #999;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.recent-tasks-container {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.task-card {
  background-color: #f8f9fa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 20px;
  transition: all 0.3s ease;
}

.task-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-color: #4a6cf7;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  flex-wrap: wrap;
  gap: 10px;
}

.task-id-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-id-info .label {
  font-weight: 500;
  color: #666;
  font-size: 14px;
}

.task-id-info .value {
  font-family: monospace;
  color: #4a6cf7;
  font-size: 14px;
}

.task-status-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  text-transform: capitalize;
}

.task-details {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-time-info {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.time-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.time-item .label {
  font-weight: 500;
  color: #666;
  font-size: 14px;
}

.time-item .value {
  color: #333;
  font-size: 14px;
}

.task-progress-info {
  display: flex;
  align-items: center;
  gap: 15px;
  flex-wrap: wrap;
}

.task-progress-info .label {
  font-weight: 500;
  color: #666;
  font-size: 14px;
  min-width: 50px;
}

.task-progress-info .progress-bar-container {
  flex: 1;
  min-width: 200px;
  height: 8px;
  background-color: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.task-progress-info .progress-bar {
  height: 100%;
  background-color: #4a6cf7;
  transition: width 0.3s ease;
}

.task-progress-info .progress-value {
  font-weight: 500;
  color: #4a6cf7;
  min-width: 40px;
  text-align: right;
}

/* 任务参数信息样式 */
.task-params-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin-top: 12px;
  padding-top: 0;
}

.param-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.param-item .label {
  font-weight: 500;
  color: #666;
  min-width: 60px;
  white-space: nowrap;
}

.param-item .value {
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

/* 时间范围字段特殊样式 */
.param-item:nth-child(4) {
  grid-column: span 2;
  min-width: 250px;
}

/* 任务ID上方的横线 */
.task-header {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e0e0e0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .data-management-nav li {
    white-space: nowrap;
    min-width: 120px;
    justify-content: center;
  }
  
  .data-actions {
    flex-direction: column;
  }
  
  .form-row {
    flex-direction: column;
    gap: 15px;
  }
  
  .form-group {
    min-width: auto;
  }
  
  .result-summary {
    grid-template-columns: 1fr;
  }
  
  .directory-overview {
    grid-template-columns: 1fr;
  }
  
  .symbol-list, .feature-list {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  }
  
  .task-time-info {
    flex-direction: column;
    gap: 10px;
    align-items: flex-start;
  }
  
  .task-progress-info {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  
  .task-progress-info .progress-bar-container {
    min-width: 100%;
  }
}
</style>