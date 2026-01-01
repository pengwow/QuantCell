import { useEffect, useState, useRef } from 'react'
import { init, dispose, registerLocale } from 'klinecharts'
import { TokenDisplay } from '../components/TokenDisplay'
import { type AppConfig } from '../utils/configLoader'
import { dataApi } from '../api'

// 扩展Window接口，添加APP_CONFIG属性
declare global {
  interface Window {
    APP_CONFIG: AppConfig;
  }
}
import {
  MenuUnfoldOutlined,
  BarChartOutlined
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
  
  // 图表实例引用
  const chartRef = useRef<any>(null)
  
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
  
  useEffect(() => {
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
        getBars: ({ callback }) => {
          // 使用API获取的数据
          callback(klineData)
        }
      })
      
      // 初始加载数据
      fetchKlineData()
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
  
  // 当搜索关键词变化时重新获取商品列表
  useEffect(() => {
    if (isSearchModalVisible) {
      fetchProducts()
    }
  }, [searchKeyword, isSearchModalVisible])

  // 工具按钮点击处理函数
  const handleToolButtonClick = (toolName: string) => {
    console.log(`点击了工具按钮: ${toolName}`);
    // 这里可以添加具体的工具功能实现
  };

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
          
          {/* 其他功能按钮 */}
          {/* <div className="function-buttons">
            <button className="func-btn" onClick={() => handleToolButtonClick('指标')}>
              <span className="func-icon">📊</span>
              <span className="func-text">指标</span>
            </button>
            <button className="func-btn" onClick={() => handleToolButtonClick('时区')}>
              <span className="func-icon">🌍</span>
              <span className="func-text">时区</span>
            </button>
            <button className="func-btn" onClick={() => handleToolButtonClick('设置')}>
              <span className="func-icon">⚙️</span>
              <span className="func-text">设置</span>
            </button>
            <button className="func-btn" onClick={() => handleToolButtonClick('截屏')}>
              <span className="func-icon">📷</span>
              <span className="func-text">截屏</span>
            </button>
            <button className="func-btn" onClick={() => handleToolButtonClick('全屏')}>
              <span className="func-icon">⛶</span>
              <span className="func-text">全屏</span>
            </button>
          </div> */}
        </div>
        
        {/* 垂直悬浮按钮列表 - 绝对定位 */}
        {isToolbarExpanded && (
          <div className="vertical-toolbar">
            <button className="vertical-btn" title="图表" onClick={() => handleToolButtonClick('图表')}>
              <BarChartOutlined />
            </button>
            <button className="vertical-btn" title="水平线" onClick={() => handleToolButtonClick('水平线')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
            </button>
            <button className="vertical-btn" title="趋势线" onClick={() => handleToolButtonClick('趋势线')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
              </svg>
            </button>
            <button className="vertical-btn" title="平行线" onClick={() => handleToolButtonClick('平行线')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="21" y1="16" x2="3" y2="16"></line>
                <line x1="21" y1="8" x2="3" y2="8"></line>
                <line x1="3" y1="8" x2="3" y2="16"></line>
              </svg>
            </button>
            <button className="vertical-btn" title="圆" onClick={() => handleToolButtonClick('圆')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
              </svg>
            </button>
            <button className="vertical-btn" title="三角形" onClick={() => handleToolButtonClick('三角形')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 2 22 22 22"></polygon>
              </svg>
            </button>
            <button className="vertical-btn" title="矩形" onClick={() => handleToolButtonClick('矩形')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              </svg>
            </button>
            <button className="vertical-btn" title="箭头" onClick={() => handleToolButtonClick('箭头')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <polyline points="19 12 12 19 5 12"></polyline>
              </svg>
            </button>
            <button className="vertical-btn" title="文字" onClick={() => handleToolButtonClick('文字')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="4" y1="7" x2="20" y2="7"></line>
                <line x1="4" y1="12" x2="20" y2="12"></line>
                <line x1="4" y1="17" x2="20" y2="17"></line>
                <line x1="10" y1="2" x2="10" y2="22"></line>
              </svg>
            </button>
            <button className="vertical-btn" title="斐波那契" onClick={() => handleToolButtonClick('斐波那契')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 2 16 6 22 6 22 18 16 18 16 22 2 22 2 16 8 16 8 6 2 6 2 2"></polyline>
              </svg>
            </button>
            <button className="vertical-btn" title="锁定" onClick={() => handleToolButtonClick('锁定')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
              </svg>
            </button>
            <button className="vertical-btn" title="眼睛" onClick={() => handleToolButtonClick('眼睛')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <circle cx="12" cy="12" r="4"></circle>
                <line x1="2" y1="12" x2="22" y2="12"></line>
              </svg>
            </button>
            <button className="vertical-btn" title="橡皮擦" onClick={() => handleToolButtonClick('橡皮擦')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"></path>
                <line x1="22" y1="2" x2="11.5" y2="12.5"></line>
              </svg>
            </button>
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
            height: '600px',
            minWidth: '600px',
            backgroundColor: '#ffffff',
            margin: '0', /* 消除可能的外边距 */
            padding: '0', /* 消除可能的内边距 */
            border: 'none', /* 移除边框，避免边框占用空间 */
            borderRadius: '0', /* 移除圆角 */
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
      
      {/* 工具栏样式 */}
      <style>{`
        .chart-toolbar {
          background-color: #ffffff;
          border: 1px solid #f0f0f0;
          border-radius: 4px;
          padding: 5px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        
        .toolbar-top {
          display: flex;
          align-items: center;
          gap: 2px; /* 减少按钮间间隙 */
          flex-wrap: wrap;
          background-color: #fafafa;
          padding: 5px;
          border-radius: 4px;
          border: 1px solid #e8e8e8;
        }
        
        .toolbar-toggle {
          cursor: pointer;
          padding: 5px;
          background-color: transparent;
          border: none;
          border-radius: 3px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s ease;
          color: #666;
          /* 调整div大小 */
          width: 36px;
          height: 36px;
        }
        
        .toolbar-toggle:hover {
          background-color: #e8f0fe;
          color: #1890ff;
        }
        
        /* 图标容器样式 */
        .toggle-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          height: 100%;
        }
        
        /* 图标样式 - 更大并添加旋转动画 */
        .toggle-icon svg {
          width: 24px;
          height: 24px;
          transition: transform 0.5s ease;
          transform: rotate(0deg);
        }
        
        /* 展开状态下图标向左旋转180度 */
        .toolbar-toggle.expanded .toggle-icon svg {
          transform: rotate(-180deg);
        }
        
        /* 商品名样式 - 添加点击效果 */
        .symbol-name {
          display: flex;
          align-items: center;
          gap: 5px;
          font-size: 16px;
          font-weight: bold;
          padding: 0 10px;
          color: #333;
          border-right: 1px solid #e8e8e8;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        
        /* 商品名悬停效果 */
        .symbol-name:hover {
          background-color: #e8f0fe;
        }
        
        .symbol-text {
          color: #333;
        }
        
        /* 时间周期按钮容器 - 相对定位 */
        .period-buttons-container {
          position: relative;
          display: inline-block;
        }
        
        .period-buttons {
          display: flex;
          // gap: 1px; /* 减少按钮间间隙 */
          background-color: white;
          /* 移除圆角 - 确保直角 */
          overflow: hidden;
          // border: 1px solid #e8e8e8;
        }
        
        .period-btn {
          padding: 4px 8px;
          border: none;
          background-color: transparent;
          cursor: pointer;
          font-size: 13px;
          transition: all 0.2s ease;
          color: #666;
          /* 明确设置为直角 */
          border-radius: 0;
          /* 移除焦点轮廓 */
          outline: none;
        }
        
        .period-btn:hover {
          background-color: #e8f0fe;
          color: #1890ff;
        }
        
        .period-btn.active {
          background-color: #1890ff;
          color: white;
          /* 明确设置选中状态为直角 */
          border-radius: 0;
        }
        
        /* 移除所有按钮的焦点轮廓 */
        button {
          outline: none;
        }
        
        /* 更多按钮特殊样式 */
        .period-btn.more-btn {
          border-left: 1px solid #e8e8e8;
          color: #1890ff;
          /* 明确设置为直角 */
          border-radius: 0;
        }
        
        .period-btn.more-btn:hover {
          background-color: #e8f0fe;
        }
        
        /* 下拉菜单样式 - 绝对定位在更多按钮下方 */
        .more-periods-dropdown {
          position: absolute;
          top: 100%; /* 在更多按钮下方 */
          right: 0; /* 右对齐 */
          background-color: white;
          border: 1px solid #e8e8e8;
          /* 移除圆角 - 确保直角 */
          overflow: hidden;
          z-index: 2000; /* 确保在最上方图层 */
          /* 平滑显示/隐藏 */
          opacity: 1;
          transition: all 0.2s ease;
          display: flex;
          flex-direction: column;
          gap: 1px;
        }
        
        /* 下拉菜单中的按钮 */
        .more-periods-dropdown .period-btn {
          width: 100%;
          text-align: center;
          border-bottom: 1px solid #e8e8e8;
        }
        
        /* 下拉菜单中最后一个按钮移除底边框 */
        .more-periods-dropdown .period-btn:last-child {
          border-bottom: none;
        }
        
        .function-buttons {
          display: flex;
          gap: 1px; /* 减少按钮间间隙 */
          margin-left: auto;
          background-color: white;
          /* 移除圆角 - 确保直角 */
          overflow: hidden;
          border: 1px solid #e8e8e8;
        }
        
        .func-btn {
          display: flex;
          align-items: center;
          gap: 3px;
          padding: 4px 8px;
          border: none;
          background-color: transparent;
          cursor: pointer;
          font-size: 13px;
          transition: all 0.2s ease;
          color: #666;
          /* 明确设置为直角 */
          border-radius: 0;
        }
        
        .func-btn:hover {
          background-color: #e8f0fe;
          color: #1890ff;
        }
        
        /* 垂直按钮样式 */
        .vertical-btn {
          width: 36px;
          height: 36px;
          border: 1px solid #d9d9d9;
          /* 明确设置为直角 */
          border-radius: 0;
          background-color: white;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.3s;
          color: #333;
        }
        
        .vertical-btn:hover {
          border-color: #1890ff;
          color: #1890ff;
          background-color: #f0f7ff;
        }
        
        .func-icon {
          font-size: 14px;
        }
        
        /* 垂直悬浮工具栏样式 - 绝对定位，在伸缩按钮下方 */
        .vertical-toolbar {
          position: absolute;
          top: 35px; /* 在伸缩按钮下方 */
          left: 0; /* 左侧对齐 */
          display: flex;
          flex-direction: column;
          gap: 8px;
          z-index: 1000; /* 确保在顶部图层 */
          background-color: rgba(255, 255, 255, 0.9);
          padding: 10px;
          border-radius: 4px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
          opacity: 1;
          transition: all 0.3s ease-in-out; /* 添加过渡动画 */
        }
        
        /* 垂直按钮样式 */
        .vertical-btn {
          width: 36px;
          height: 36px;
          border: 1px solid #d9d9d9;
          border-radius: 4px;
          background-color: white;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.3s;
          color: #333;
        }
        
        .vertical-btn:hover {
          border-color: #1890ff;
          color: #1890ff;
          background-color: #f0f7ff;
        }
        
        /* 确保图表容器不受工具栏影响 */
        .chart-toolbar-container {
          position: relative;
          margin-bottom: 0 !important; /* 消除工具栏和图表之间的间隔 */
          padding-bottom: 0 !important;
        }
        
        /* 确保k-line-chart div与内部canvas之间没有间隔 */
        .k-line-chart {
          margin: 0 !important;
          padding: 0 !important;
          line-height: 0 !important;
          border: none !important; /* 移除边框，避免边框占用空间 */
          border-radius: 0 !important;
        }
        
        /* 确保canvas元素与容器之间没有间隔 */
        .k-line-chart canvas {
          display: block !important;
          vertical-align: top !important;
          margin: 0 !important;
          padding: 0 !important;
        }
        
        /* 图表容器 */
        .chart-container {
          position: relative;
          width: 100%;
          height: 600px; /* 确保完整显示横轴 */
          margin-top: 0 !important;
          padding-top: 0 !important;
        }
        
        /* 图表加载状态 */
        .chart-loading {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          display: flex;
          justify-content: center;
          align-items: center;
          background-color: rgba(255, 255, 255, 0.8);
          z-index: 100;
        }
        
        /* 图表错误信息 */
        .chart-error {
          position: absolute;
          top: 20px;
          left: 20px;
          right: 20px;
          z-index: 100;
        }
      `}</style>
    </div>
  )
}
