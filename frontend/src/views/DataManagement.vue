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
      </main>
    </div>

    <!-- 操作成功提示 -->
    <div v-if="showSuccessMessage" class="success-message">
      {{ successMessage }}
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, reactive, ref } from 'vue'

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
      { id: 'quality', title: '数据质量', icon: 'icon-quality' },
      { id: 'visualization', title: '数据可视化', icon: 'icon-visualization' }
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
      exportChart
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
  gap: 30px;
  min-height: 600px;
}

.data-management-sidebar {
  width: 240px;
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

/* 响应式设计 */
@media (max-width: 768px) {
  .data-management-content {
    flex-direction: column;
  }
  
  .data-management-sidebar {
    width: 100%;
  }
  
  .data-management-nav ul {
    display: flex;
    overflow-x: auto;
    border-radius: 8px;
  }
  
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
}
</style>