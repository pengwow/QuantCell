import { useEffect, useState, useRef, useCallback } from 'react'
import { init, dispose, registerLocale, registerOverlay, registerIndicator } from 'klinecharts'
// 导入自定义绘图工具扩展
import overlays from '../extension/index'
import { TokenDisplay } from '../components/TokenDisplay'
import DrawingBar from '../components/DrawingBar'
import IndicatorToolbar from '../components/IndicatorToolbar'
import { RealtimeToggleButton } from '../components/RealtimeToggleButton'
import { type AppConfig } from '../utils/configLoader'
import { dataApi } from '../api'
import realtimeApi from '../api/realtimeApi'
import { type Indicator, type ActiveIndicator } from '../hooks/useIndicators'
import '../styles/ChartPage.css'

// 实时数据更新配置
const REALTIME_UPDATE_CONFIG = {
  // 节流间隔(ms)，限制更新频率
  throttleInterval: 100,
  // 最大可见K线数量
  maxVisibleBars: 200,
  // 批量更新阈值
  batchThreshold: 5,
  // 批量更新间隔(ms)
  batchInterval: 200,
}

// 扩展Window接口，添加APP_CONFIG属性
declare global {
  interface Window {
    APP_CONFIG: AppConfig;
  }
}
import {
  MenuUnfoldOutlined
} from '@ant-design/icons';
import {
  Modal,
  Input,
  Spin,
  Alert
} from 'antd';


// 注册繁体中文语言包
registerLocale('zh-HK', {
  time: '時間：',
  open: '開：',
  high: '高：',
  low: '低：',
  close: '收：',
  volume: '成交量：',
  change: '漲跌：',
  turnover: '成交額：',
  second: '秒',
  minute: '分',
  hour: '時',
  day: '日',
  week: '週',
  month: '月',
  year: '年'
})

export default function ChartPage () {
  // 控制工具栏展开状态
  const [isToolbarExpanded, setIsToolbarExpanded] = useState(false)
  // 控制周期按钮展开状态
  const [isPeriodsExpanded, setIsPeriodsExpanded] = useState(false)
  // 控制商品搜索弹窗显示状态
  const [isSearchModalVisible, setIsSearchModalVisible] = useState(false)
  // 当前选中的周期
  const [selectedPeriod, setSelectedPeriod] = useState('15m')
  // 当前商品信息
  const [currentSymbol, setCurrentSymbol] = useState({
    code: 'BTC/USDT',
    name: 'Bitcoin/USDT',
    icon: 'S', // 默认股票图标
    base: 'BTC'
  })
  // 当前语言配置 - 从全局APP_CONFIG读取
  const [language, setLanguage] = useState(window.APP_CONFIG?.language || 'zh-CN')
  // 搜索关键词
  const [searchKeyword, setSearchKeyword] = useState('')
  
  // 数据加载状态
  const [loading, setLoading] = useState(false)
  // 错误状态
  const [error, setError] = useState<string | null>(null)
  // K线数据
  const [klineData, setKlineData] = useState<any[]>([])
  // 市场类型
  const [marketType] = useState('crypto')
  // 加密货币类型
  const [cryptoType] = useState('spot')
  // 商品列表数据
  const [products, setProducts] = useState<any[]>([])
  // 商品列表加载状态
  const [productsLoading, setProductsLoading] = useState(false)
  // 商品列表错误信息
  const [productsError, setProductsError] = useState<string | null>(null)
  
  // 指标相关状态
  const [activeIndicators, setActiveIndicators] = useState<ActiveIndicator[]>([])
  
  // 系统配置状态 - 实时数据开关
  const [systemConfig, setSystemConfig] = useState({
    realtime_enabled: false,
    data_mode: 'cache' as 'realtime' | 'cache',
  })
  
  // 实时数据状态
  const [isRealtimeActive, setIsRealtimeActive] = useState(false)

  // 图表实例引用
  const chartRef = useRef<any>(null)

  // 实时数据更新相关引用
  const realtimeDataQueueRef = useRef<any[]>([])
  const lastUpdateTimeRef = useRef<number>(0)
  const batchUpdateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isProcessingRef = useRef<boolean>(false)
  const latestBarRef = useRef<any>(null)
  const klineDataRef = useRef<any[]>([])
  
  // 本地存储相关常量和函数
  const STORAGE_KEY = 'chart_user_preferences';
  
  /**
   * 保存用户偏好设置到本地存储
   * @param symbol 商品代码
   * @param period 时间周期
   */
  const saveUserPreferences = (symbol: string, period: string) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ symbol, period }));
  };
  
  /**
   * 从本地存储读取用户偏好设置
   * @returns 用户偏好设置对象或null
   */
  const getUserPreferences = () => {
    const preferences = localStorage.getItem(STORAGE_KEY);
    return preferences ? JSON.parse(preferences) : null;
  };
  
  // 监听APP_CONFIG.language变化
  useEffect(() => {
    // 当APP_CONFIG.language变化时更新语言状态
    const updateLanguage = () => {
      const currentLanguage = window.APP_CONFIG?.language || 'zh-CN';
      setLanguage(currentLanguage);
    };

    // 初始调用
    updateLanguage();

    // 可以考虑添加一个事件监听机制，当APP_CONFIG变化时自动更新
    // 这里简单实现，组件挂载时检查一次
  }, []);

  // 组件挂载时获取系统配置
  useEffect(() => {
    const fetchSystemConfig = async () => {
      try {
        const config = await realtimeApi.getRealtimeConfig()
        if (config) {
          setSystemConfig({
            realtime_enabled: config.realtime_enabled,
            data_mode: config.data_mode,
          })
        }
      } catch (err) {
        console.error('获取系统配置失败:', err)
      }
    }

    fetchSystemConfig()
  }, [])
  
  // 组件挂载时读取本地存储的偏好设置
  useEffect(() => {
    const preferences = getUserPreferences();
    if (preferences) {
      // 更新周期状态
      setSelectedPeriod(preferences.period);
      // 商品将在fetchProducts后更新
    }
  }, []);
  
  // 周期列表 - 分为常用和不常用
  const commonPeriods = ['1m', '5m', '15m', '1H', '4H', '1D'] // 常用周期
  const morePeriods = ['2H', '1W', '1M', '1Y'] // 不常用周期
  
  // 获取K线数据的函数
  const fetchKlineData = async () => {
    setLoading(true)
    setError(null)

    try {
      // 调用API获取K线数据
      const data = await dataApi.getKlines({
        symbol: currentSymbol.code,
        interval: selectedPeriod,
        market_type: marketType,
        crypto_type: cryptoType,
        limit: 5000
      })

      setKlineData(data)
      // 同步到 ref，供实时更新使用
      klineDataRef.current = data
    } catch (err) {
      console.error('获取K线数据失败:', err)
      setError('获取K线数据失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }
  
  // 辅助函数：根据周期字符串获取周期数值
  const getPeriodSpan = (period: string) => {
    // 提取周期数值部分
    const match = period.match(/\d+/)
    if (match) {
      return parseInt(match[0])
    }
    // 默认返回1
    return 1
  }
  
  // 辅助函数：根据周期字符串获取周期类型
  const getPeriodType = (period: string) => {
    if (period.includes('m')) {
      return 'minute'
    } else if (period.includes('H')) {
      return 'hour'
    } else if (period.includes('D')) {
      return 'day'
    } else if (period.includes('W')) {
      return 'week'
    } else if (period.includes('M')) {
      return 'month'
    } else if (period.includes('Y')) {
      return 'year'
    }
    // 默认返回day
    return 'day'
  }
 // 组件挂载时初始化图表
  useEffect(() => {
    // 注册自定义绘图工具扩展
    overlays.forEach(overlay => {
      registerOverlay(overlay)
    })
    
    // 初始化图表，传递语言选项
    const chart = init('language-k-line', { locale: language })
    chartRef.current = chart
    
    // 确保图表初始化成功
    if (chart) {
      // 设置交易对信息
      chart.setSymbol({ ticker: currentSymbol.code })
      
      // 动态设置周期
      chart.setPeriod({ span: getPeriodSpan(selectedPeriod), type: getPeriodType(selectedPeriod) })
      
      // 设置数据加载器
      chart.setDataLoader({
        getBars: ({ callback }: { callback: (data: any[]) => void }) => {
          // 使用API获取的数据
          callback(klineData)
        }
      })
      
      // 初始加载数据
      fetchKlineData()

      // 自动选中VOL指标（如果尚未选中）
      setTimeout(() => {
        if (!chartRef.current) return

        try {
          // 检查图表中是否已存在VOL指标
          const existingIndicators = chartRef.current.getIndicators() || []
          const hasVolIndicator = existingIndicators.some((ind: any) => ind.name === 'VOL')

          if (hasVolIndicator) return

          // 在图表中创建VOL指标
          chartRef.current.createIndicator('VOL', true)

          // 同步更新活跃指标列表
          setActiveIndicators(prev => {
            // 再次检查状态层是否已存在
            if (prev.find(ind => String(ind.id) === 'vol')) return prev

            const volIndicator: ActiveIndicator = {
              id: 'vol' as unknown as number,
              name: 'VOL',
              description: '成交量指标',
              code: '',
              user_id: 0,
              is_buy: 0,
              end_time: 1,
              publish_to_community: 0,
              pricing_type: 'free',
              price: 0,
              is_encrypted: 0,
            }
            return [...prev, volIndicator]
          })
        } catch (err) {
          console.error('创建VOL指标失败:', err)
        }
      }, 500)
    }

    // 组件卸载时销毁图表
    return () => {
      dispose('language-k-line')
      chartRef.current = null
    }
  }, [currentSymbol.code, selectedPeriod, language])
  
  // 获取商品列表的函数
  const fetchProducts = async () => {
    setProductsLoading(true)
    setProductsError(null)
    
    try {
      // 调用API获取商品列表
      const response = await dataApi.getProducts({
        market_type: marketType,
        crypto_type: cryptoType,
        exchange: 'binance', // 默认使用binance交易商，可根据系统配置调整
        filter: searchKeyword || undefined,
        limit: 100
      })
      
      const productsList = response.products || [];
      setProducts(productsList);
      
      // 如果商品列表不为空，检查是否需要更新默认商品
      if (productsList.length > 0) {
        const preferences = getUserPreferences();
        
        // 情况1：有本地存储的偏好，且当前商品不是偏好的商品
          if (preferences && currentSymbol.code !== preferences.symbol) {
            // 查找偏好的商品
            const preferredProduct = productsList.find((product: any) => product.symbol === preferences.symbol);
            if (preferredProduct) {
              setCurrentSymbol({
                code: preferredProduct.symbol,
                name: preferredProduct.name,
                icon: preferredProduct.icon,
                base: preferredProduct.base
              });
            }
          } 
        // 情况2：没有本地存储的偏好，且当前商品是默认的BABA
        else if (!preferences && currentSymbol.code === 'BABA') {
          // 使用列表第一个商品作为默认商品
          const firstProduct = productsList[0];
          setCurrentSymbol({
            code: firstProduct.symbol,
            name: firstProduct.name,
            icon: firstProduct.icon,
            base: firstProduct.base
          });
          saveUserPreferences(firstProduct.symbol, selectedPeriod);
        }
      }
    } catch (err) {
      console.error('获取商品列表失败:', err)
      setProductsError('获取商品列表失败，请稍后重试')
    } finally {
      setProductsLoading(false)
    }
  }
  
  // 当klineData变化时更新图表
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.setDataLoader({
        getBars: ({ callback }: { callback: (data: any[]) => void }) => {
          callback(klineData)
        }
      })
    }
  }, [klineData])
  
  // 当周期变化时更新图表周期
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.setPeriod({ span: getPeriodSpan(selectedPeriod), type: getPeriodType(selectedPeriod) })
    }
  }, [selectedPeriod])
  
  // 当周期或商品变化时重新获取数据
  useEffect(() => {
    fetchKlineData()
  }, [selectedPeriod, currentSymbol.code, marketType, cryptoType])
  
  // 监听图表容器大小变化，调整图表宽度
  useEffect(() => {
    const chartElement = document.getElementById('language-k-line')
    let resizeObserver: ResizeObserver | null = null
    
    const handleResize = () => {
      if (chartRef.current) {
        // 强制图表重新计算大小
        chartRef.current.resize()
      }
    }
    
    // 使用ResizeObserver监听容器大小变化
    if (chartElement && typeof ResizeObserver === 'function') {
      resizeObserver = new ResizeObserver(handleResize)
      resizeObserver.observe(chartElement)
    }
    
    // 同时监听窗口大小变化作为备份
    window.addEventListener('resize', handleResize)
    
    // 初始加载时也调整一次
    handleResize()
    
    // 组件卸载时移除监听器
    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect()
      }
      window.removeEventListener('resize', handleResize)
    }
  }, [])
  
  // 当搜索关键词变化时重新获取商品列表
  useEffect(() => {
    if (isSearchModalVisible) {
      fetchProducts()
    }
  }, [searchKeyword, isSearchModalVisible])

  // 批量处理实时数据更新
  const processBatchUpdate = useCallback(() => {
    if (!chartRef.current || realtimeDataQueueRef.current.length === 0) return

    const chart = chartRef.current
    const queue = realtimeDataQueueRef.current

    try {
      // 获取当前所有数据
      const currentData = klineDataRef.current || []

      // 处理队列中的数据
      queue.forEach((data) => {
        // 处理多种可能的数据格式
        let kline = data.k

        if (!kline && data.data) {
          kline = data.data.k || data.data
        }

        if (!kline && data.data && data.data.data) {
          kline = data.data.data.k || data.data.data
        }

        if (!kline) {
          return
        }

        // 解析K线数据
        const bar = {
          timestamp: kline.t,
          open: parseFloat(kline.o),
          high: parseFloat(kline.h),
          low: parseFloat(kline.l),
          close: parseFloat(kline.c),
          volume: parseFloat(kline.v),
        }

        // 检查是否已存在相同时间戳的数据
        const existingIndex = currentData.findIndex(
          (item: any) => item.timestamp === bar.timestamp
        )

        if (existingIndex >= 0) {
          currentData[existingIndex] = bar
        } else {
          currentData.push(bar)
        }

        // 保存最新数据
        latestBarRef.current = bar
      })

      // 限制数据量，只保留最近 maxVisibleBars 条
      if (currentData.length > REALTIME_UPDATE_CONFIG.maxVisibleBars) {
        const startIndex = currentData.length - REALTIME_UPDATE_CONFIG.maxVisibleBars
        klineDataRef.current = currentData.slice(startIndex)
      } else {
        klineDataRef.current = currentData
      }

      // 使用 requestAnimationFrame 优化渲染
      requestAnimationFrame(() => {
        if (!chartRef.current) return

        // 使用 setDataLoader 重新加载数据（klinecharts 推荐方式）
        chartRef.current.setDataLoader({
          getBars: ({ callback }: { callback: (data: any[]) => void }) => {
            callback(klineDataRef.current)
          }
        })

        // 触发图表重绘
        chartRef.current.resize()
      })

      // 清空队列
      realtimeDataQueueRef.current = []

      // 简化日志输出
      console.log(`[Realtime] 批量更新完成: 处理${queue.length}条, 总计${klineDataRef.current.length}条`)
    } catch (err) {
      console.error('[Realtime] 批量处理数据失败:', err)
    }
  }, [])

  // 处理实时数据更新（带节流）
  const handleRealtimeData = useCallback((data: any) => {
    if (!data) {
      console.warn('[Realtime] 接收到空数据')
      return
    }

    const now = Date.now()
    const timeSinceLastUpdate = now - lastUpdateTimeRef.current

    // 解析K线数据
    let kline = data.k
    if (!kline && data.data) {
      kline = data.data.k || data.data
    }
    if (!kline && data.data && data.data.data) {
      kline = data.data.data.k || data.data.data
    }

    if (kline) {
      // 简化日志输出，只记录关键信息
      console.log(`[Realtime] 收到K线: ${kline.s}@${kline.i}, close=${kline.c}, queue=${realtimeDataQueueRef.current.length + 1}`)
    }

    // 将数据加入队列
    realtimeDataQueueRef.current.push(data)

    // 检查是否需要立即更新（超过节流间隔）
    if (timeSinceLastUpdate >= REALTIME_UPDATE_CONFIG.throttleInterval) {
      // 清除定时器
      if (batchUpdateTimerRef.current) {
        clearTimeout(batchUpdateTimerRef.current)
        batchUpdateTimerRef.current = null
      }

      // 立即处理
      lastUpdateTimeRef.current = now
      processBatchUpdate()
    } else {
      // 设置批量更新定时器
      if (!batchUpdateTimerRef.current) {
        batchUpdateTimerRef.current = setTimeout(() => {
          lastUpdateTimeRef.current = Date.now()
          processBatchUpdate()
          batchUpdateTimerRef.current = null
        }, REALTIME_UPDATE_CONFIG.batchInterval)
      }
    }

    // 如果队列超过阈值，立即处理
    if (realtimeDataQueueRef.current.length >= REALTIME_UPDATE_CONFIG.batchThreshold) {
      console.log(`[Realtime] 队列超过阈值 (${REALTIME_UPDATE_CONFIG.batchThreshold})，立即处理`)
      if (batchUpdateTimerRef.current) {
        clearTimeout(batchUpdateTimerRef.current)
        batchUpdateTimerRef.current = null
      }
      lastUpdateTimeRef.current = now
      processBatchUpdate()
    }
  }, [processBatchUpdate])

  // 处理实时状态变化
  const handleRealtimeStatusChange = (isActive: boolean) => {
    setIsRealtimeActive(isActive)
  }

  // 内置指标名称映射（将自定义ID映射到KLineCharts内置指标）
  const builtInIndicatorMap: Record<string, string> = {
    'vol': 'VOL',
    'sma': 'MA',
    'ema': 'EMA',
    'rsi': 'RSI',
    'macd': 'MACD',
    'bb': 'BOLL',
    'atr': 'ATR',
    'cci': 'CCI',
    'wr': 'WR'
  }

  // 注册自定义指标到KLineCharts
  const registerCustomIndicator = (indicator: Indicator, data: any) => {
    const indicatorName = `custom_${indicator.id}`

    // 注册自定义指标
    registerIndicator({
      name: indicatorName,
      shortName: indicator.name,
      calc: (kLineDataList: any[]) => {
        // 将K线数据与指标计算结果合并
        return kLineDataList.map((kLine) => {
          // 找到对应时间戳的指标数据
          const indicatorData = data?.find((d: any) => d.timestamp === kLine.timestamp)
          return {
            ...kLine,
            // 添加指标值到K线数据
            [indicatorName]: indicatorData?.value || null
          }
        })
      },
      figures: [
        {
          key: indicatorName,
          type: 'line'
        }
      ]
    })

    return indicatorName
  }

  // 处理指标切换
  const handleToggleIndicator = async (indicator: Indicator, params?: Record<string, any>) => {
    // 检查是否是内置指标（通过特殊标记或ID类型判断）
    const builtInId = params?._builtInId
    const indicatorId = builtInId ? String(builtInId) : String(indicator.id)

    setActiveIndicators(prev => {
      const exists = prev.find(ind => ind.id === indicator.id)
      if (exists) {
        // 停止指标 - 从图表中移除
        if (chartRef.current) {
          // 获取所有指标实例
          const indicators = chartRef.current.getIndicators()
          indicators.forEach((ind: any) => {
            // 根据指标名称或paneId判断是否为目标指标
            if (ind.name === indicatorId || ind.name === builtInIndicatorMap[indicatorId] || ind.name === `custom_${indicator.id}`) {
              chartRef.current?.removeIndicator({ paneId: ind.paneId, indicatorName: ind.name })
            }
          })
        }
        return prev.filter(ind => ind.id !== indicator.id)
      }
      return prev
    })

    // 如果是启动指标，添加到图表
    if (!activeIndicators.find(ind => ind.id === indicator.id)) {
      // 启动指标
      const activeIndicator: ActiveIndicator = {
        ...indicator,
        userParams: params
      }

      // 添加到活跃指标列表
      setActiveIndicators(prev => [...prev, activeIndicator])

      // 添加到图表
      if (chartRef.current) {
        // 检查是否是内置指标
        const builtInName = builtInIndicatorMap[indicatorId]

        if (builtInName) {
          // 内置指标：直接使用KLineCharts的createIndicator
          try {
            // 创建指标，根据类型决定是否叠加在主图上
            const isOverlay = ['MA', 'EMA', 'BOLL', 'SAR', 'BBI', 'SMA'].includes(builtInName)

            if (isOverlay) {
              // 叠加在蜡烛图上
              chartRef.current.createIndicator(builtInName, false, { id: 'candle_pane' })
            } else {
              // 创建独立pane显示
              chartRef.current.createIndicator(builtInName, true)
            }
          } catch (err) {
            console.error('创建内置指标失败:', err)
          }
        } else {
          // 自定义指标：调用API获取计算结果，然后注册并显示
          try {
            // 调用后端API获取指标计算结果
            const response = await fetch(`/api/indicators/${indicator.id}/execute`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                symbol: currentSymbol.code,
                period: selectedPeriod,
                params: params || {}
              })
            })

            const result = await response.json()

            if (result.success && result.data) {
              // 注册自定义指标
              const customIndicatorName = registerCustomIndicator(indicator, result.data)

              // 创建自定义指标
              chartRef.current.createIndicator(customIndicatorName, true)
            } else {
              console.error('获取指标数据失败:', result.message)
            }
          } catch (err) {
            console.error('执行自定义指标失败:', err)
          }
        }
      }
    }
  }

  return (
    <div className="chart-page-container">
      {/* 工具栏容器 */}
      <div className="chart-toolbar-container">
        {/* 顶部工具栏 */}
        <div className="toolbar-top">
          {/* 伸缩按钮 */}
          <div 
            className={`toolbar-toggle ${isToolbarExpanded ? 'expanded' : ''}`} 
            onClick={() => setIsToolbarExpanded(!isToolbarExpanded)}
          >
            <span className="toggle-icon">
              <MenuUnfoldOutlined />
            </span>
          </div>
          
          {/* 商品名 - 点击弹出搜索框 */}
          <div className="symbol-name" onClick={() => setIsSearchModalVisible(true)}>
            <TokenDisplay symbol={currentSymbol.base} size={20} style={{ marginRight: '8px' }} />
            <span className="symbol-text">{currentSymbol.code}</span>
          </div>
          
          {/* 时间周期切换 - 分为常用和更多 */}
          <div className="period-buttons-container">
            {/* 常用周期和更多按钮容器 */}
            <div className="period-buttons">
              {/* 常用周期 */}
            {commonPeriods.map((period) => (
              <button
                key={period}
                className={`period-btn ${selectedPeriod === period ? 'active' : ''}`}
                onClick={() => {
                  setSelectedPeriod(period);
                  // 保存用户偏好设置
                  saveUserPreferences(currentSymbol.code, period);
                }}
              >
                {period}
              </button>
            ))}
            {/* 更多按钮 */}
            <button
              className="period-btn more-btn"
              onClick={() => setIsPeriodsExpanded(!isPeriodsExpanded)}
            >
              {isPeriodsExpanded ? '收起' : '更多'}
            </button>
            </div>
            {/* 不常用周期 - 绝对定位在更多按钮下方 */}
            {isPeriodsExpanded && (
              <div 
                className="more-periods-dropdown"
                onMouseLeave={() => setIsPeriodsExpanded(false)}
              >
                {morePeriods.map((period) => (
                  <button
                    key={period}
                    className={`period-btn ${selectedPeriod === period ? 'active' : ''}`}
                    onClick={() => {
                      setSelectedPeriod(period)
                      // 保存用户偏好设置
                      saveUserPreferences(currentSymbol.code, period);
                      setIsPeriodsExpanded(false) // 选择后自动收起
                    }}
                  >
                    {period}
                  </button>
                ))}
              </div>
            )}
          </div>
          
          {/* 指标工具栏 */}
          <div className="indicator-toolbar-wrapper">
            <IndicatorToolbar
              activeIndicators={activeIndicators}
              onToggleIndicator={handleToggleIndicator}
            />
          </div>

          {/* 实时数据控制按钮 */}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
            <RealtimeToggleButton
              symbol={currentSymbol.code.replace('/', '')}
              period={selectedPeriod.toLowerCase()}
              defaultRealtimeEnabled={systemConfig.realtime_enabled}
              onRealtimeData={handleRealtimeData}
              onStatusChange={handleRealtimeStatusChange}
            />
          </div>
        </div>
        
        {/* 绘图工具栏 */}
        {isToolbarExpanded && (
          <div className="vertical-toolbar">
            <DrawingBar
              onDrawingItemClick={(overlay) => {
                console.log('Drawing item clicked:', overlay);
                if (chartRef.current) {
                  // 调用klinecharts的绘图API，创建绘图对象
                  chartRef.current.createOverlay({
                    name: overlay.name,
                    groupId: overlay.groupId || 'drawing_tools',
                    lock: overlay.lock,
                    mode: overlay.mode as 'normal' | 'weak_magnet' | 'strong_magnet',
                    visible: true
                  });
                }
              }}
              onModeChange={(mode) => {
                console.log('Mode changed:', mode);
                // 当前klinecharts版本不支持全局设置绘图模式，模式在创建overlay时指定
              }}
              onLockChange={(lock) => {
                console.log('Lock changed:', lock);
                if (chartRef.current) {
                  // 获取所有绘图对象并设置锁定状态
                  const overlays = chartRef.current.getOverlays({ groupId: 'drawing_tools' });
                  overlays.forEach((overlay: any) => {
                    chartRef.current?.overrideOverlay({ id: overlay.id, lock });
                  });
                }
              }}
              onVisibleChange={(visible) => {
                console.log('Visible changed:', visible);
                if (chartRef.current) {
                  // 获取所有绘图对象并设置可见性
                  const overlays = chartRef.current.getOverlays({ groupId: 'drawing_tools' });
                  overlays.forEach((overlay: any) => {
                    chartRef.current?.overrideOverlay({ id: overlay.id, visible });
                  });
                }
              }}
              onRemoveClick={(groupId) => {
                console.log('Remove clicked:', groupId);
                if (chartRef.current) {
                  // 删除指定分组的所有绘图对象
                  chartRef.current.removeOverlay({ groupId });
                }
              }}
            />
          </div>
        )}
      </div>

      {/* 图表容器 - 使用固定宽高确保图表正确渲染 */}
      <div className="chart-container">
        {/* 加载状态 */}
        {loading && (
          <div className="chart-loading">
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <Spin size="large" />
              <div style={{ marginTop: 8 }}>加载中...</div>
            </div>
          </div>
        )}

        {/* 错误信息 */}
        {error && (
          <div className="chart-error">
            <Alert message="错误" description={error} type="error" showIcon />
          </div>
        )}

        <div
          id="language-k-line"
          className="k-line-chart"
          style={{
            width: '100%',
            height: '100%',
            // 移除固定最小宽度限制，允许图表在小屏幕上自适应
            minWidth: 'auto',
            maxWidth: '100%',
            backgroundColor: '#ffffff',
            margin: '0', /* 消除可能的外边距 */
            padding: '0', /* 消除可能的内边距 */
            border: 'none', /* 移除边框，避免边框占用空间 */
            borderRadius: '0', /* 移除圆角 */
            boxSizing: 'border-box', /* 确保宽度计算包含内边距和边框 */
          }}
        />
      </div>

      {/* 商品搜索弹窗 - 使用Ant Design组件 */}
      <Modal
        title="商品搜索"
        open={isSearchModalVisible}
        onCancel={() => setIsSearchModalVisible(false)}
        footer={null}
        width={600}
      >
        {/* 搜索输入框 */}
        <Input
          placeholder="商品代码"
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          allowClear
          style={{ marginBottom: 16 }}
        />
        
        {/* 商品列表 - 使用div和map替代List组件 */}
        <div style={{ maxHeight: 'calc(80vh - 200px)', overflowY: 'auto' }}>
          {/* 加载状态 */}
          {productsLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
              <Spin size="large" />
              <div style={{ marginTop: 8 }}>加载中...</div>
            </div>
          ) : productsError ? (
            /* 错误信息 */
            <div style={{ padding: '20px' }}>
              <Alert message="错误" description={productsError} type="error" showIcon />
            </div>
          ) : products.length === 0 ? (
            /* 无数据提示 */
            <div style={{ textAlign: 'center', padding: '20px', color: '#999' }}>
              未找到匹配的商品
            </div>
          ) : (
            /* 商品列表 */
            products.map((product) => (
              <div
                key={product.symbol}
                onClick={() => {
                  setCurrentSymbol({
                    code: product.symbol,
                    name: product.name,
                    icon: product.icon,
                    base: product.base,
                  })
                  // 保存用户偏好设置
                  saveUserPreferences(product.symbol, selectedPeriod);
                  setIsSearchModalVisible(false)
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '12px 20px',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s ease',
                  borderBottom: '1px solid #f0f0f0'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#fafafa'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                {/* 商品图标 */}
                <div style={{ marginRight: '12px' }}>
                  <TokenDisplay symbol={product.base} size={20} />
                </div>
                
                {/* 商品信息 */}
                <div style={{ flex: 1 }}>
                  <div>
                    <span style={{ marginRight: '8px', fontWeight: 'bold' }}>{product.symbol}</span>
                    <span style={{ color: '#666', fontSize: '14px' }}>({product.name})</span>
                  </div>
                </div>
                
                {/* 交易所信息 */}
                <span style={{ color: '#999', fontSize: '14px' }}>
                  {product.exchange}
                </span>
              </div>
            ))
          )}
        </div>
      </Modal>
      
    </div>
  )
}
