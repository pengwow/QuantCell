/**
 * 回测回放页面组件
 * 功能：展示回测结果的历史回放，支持播放、暂停、进度调整及倍速控制
 */
import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import * as klinecharts from 'klinecharts';
import { backtestApi } from '../api';
import '../styles/BacktestReplay.css';

// 回放数据类型定义
interface ReplayData {
  kline_data: any[];
  trade_signals: any[];
  equity_data: any[];
}

const BacktestReplay = () => {
  // 获取URL参数中的回测ID
  const { backtestId } = useParams<{ backtestId: string }>();

  // 回放数据
  const [replayData, setReplayData] = useState<ReplayData | null>(null);

  // 回放状态
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [speed, setSpeed] = useState<number>(1); // 播放速度，1x, 2x, etc.
  const [progress, setProgress] = useState<number>(0);

  // 加载状态
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // 图表引用
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any | null>(null); // 使用any类型兼容不同版本的klinecharts API
  const animationFrameRef = useRef<number | null>(null);
  const lastUpdateTimeRef = useRef<number>(0);

  /**
   * 加载回放数据
   */
  const loadReplayData = async () => {
    if (!backtestId) {
      setError('回测ID不能为空');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await backtestApi.getReplayData(backtestId);
      if (response.status === 'success' && response.data) {
        setReplayData(response.data);
      } else {
        setError(response.message || '加载回放数据失败');
      }
    } catch (err) {
      console.error('加载回放数据失败:', err);
      setError('加载回放数据失败');
    } finally {
      setLoading(false);
    }
  };

  /**
   * 初始化图表
   */
  const initChart = () => {
    if (!chartContainerRef.current || !replayData) return;

    // 创建图表实例 (兼容klinecharts 10.0.0-beta1 API)
    chartRef.current = klinecharts.init(chartContainerRef.current);

    // 设置图表配置
    chartRef.current.setOption({
      layout: {
        backgroundColor: '#18191d',
        textColor: '#a3a9b4'
      },
      crosshair: {
        x: {
          enabled: true,
          style: {
            color: '#333842',
            dashStyle: [5, 5]
          }
        },
        y: {
          enabled: true,
          style: {
            color: '#333842',
            dashStyle: [5, 5]
          }
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        top: '3%',
        bottom: '30%'
      },
      styles: {
        candle: {
          upColor: '#ef5350',
          downColor: '#26a69a',
          borderColor: 'rgba(0, 0, 0, 0.5)',
          borderDownColor: 'rgba(0, 0, 0, 0.5)'
        }
      }
    });

    // 更新图表数据
    updateChartData(0);
    renderTradeSignals(0);
  };

  /**
   * 更新图表数据
   * @param index 当前数据索引
   */
  const updateChartData = (index: number) => {
    if (!chartRef.current || !replayData) return;

    // 获取截至当前索引的数据
    const currentKlineData = replayData.kline_data.slice(0, index + 1);

    // 转换为klinecharts所需的数据格式
    const chartData = currentKlineData.map(item => ({
      timestamp: new Date(item.time).getTime(),
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
      volume: item.volume
    }));

    // 更新图表数据
    chartRef.current.applyNewData(chartData);
  };

  /**
   * 渲染交易信号
   * @param index 当前数据索引
   */
  const renderTradeSignals = (index: number) => {
    if (!chartRef.current || !replayData) return;

    // 清除现有标记
    chartRef.current.removeAllMarkLines();
    chartRef.current.removeAllMarkPoints();

    // 获取截至当前索引的K线数据
    const currentKlineData = replayData.kline_data.slice(0, index + 1);
    if (currentKlineData.length === 0) return;

    // 获取最后一根K线的时间
    const lastKlineTime = new Date(currentKlineData[currentKlineData.length - 1].time).getTime();

    // 查找当前时间之前的交易信号
    const currentSignals = replayData.trade_signals.filter(signal => {
      const signalTime = new Date(signal.time).getTime();
      return signalTime <= lastKlineTime;
    });

    // 添加交易信号标记
    currentSignals.forEach(signal => {
      const signalTime = new Date(signal.time).getTime();
      const markPointType = signal.type === 'buy' ? 'arrowUp' : 'arrowDown';
      const markPointColor = signal.type === 'buy' ? '#26a69a' : '#ef5350';

      // 添加标记点
      chartRef.current?.addMarkPoint({
        id: `signal_${signal.trade_id}`,
        data: [{
          timestamp: signalTime,
          price: signal.price,
          type: markPointType,
          color: markPointColor,
          text: signal.type === 'buy' ? '买' : '卖',
          textColor: '#fff',
          size: 20
        }]
      });
    });
  };

  /**
   * 播放回放
   */
  const playReplay = () => {
    setIsPlaying(true);
  };

  /**
   * 暂停回放
   */
  const pauseReplay = () => {
    setIsPlaying(false);
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  };

  /**
   * 停止回放
   */
  const stopReplay = () => {
    setIsPlaying(false);
    setCurrentIndex(0);
    setProgress(0);
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    // 更新图表
    updateChartData(0);
    renderTradeSignals(0);
  };

  /**
   * 调整进度
   * @param newProgress 新的进度值（0-100）
   */
  const adjustProgress = (newProgress: number) => {
    if (!replayData) return;

    const newIndex = Math.floor((newProgress / 100) * (replayData.kline_data.length - 1));
    setCurrentIndex(newIndex);
    setProgress(newProgress);

    // 更新图表
    updateChartData(newIndex);
    renderTradeSignals(newIndex);
  };

  /**
   * 调整播放速度
   * @param newSpeed 新的播放速度（1x, 2x, etc.）
   */
  const adjustSpeed = (newSpeed: number) => {
    setSpeed(newSpeed);
  };

  /**
   * 动画循环函数
   */
  const animate = (timestamp: number) => {
    if (!replayData || !isPlaying) return;

    if (!lastUpdateTimeRef.current) {
      lastUpdateTimeRef.current = timestamp;
    }

    // 计算时间差
    const elapsedTime = timestamp - lastUpdateTimeRef.current;
    const frameInterval = 1000 / speed; // 根据速度调整帧间隔

    if (elapsedTime >= frameInterval) {
      // 更新索引
      setCurrentIndex(prevIndex => {
        const newIndex = prevIndex + 1;
        if (newIndex >= replayData.kline_data.length - 1) {
          // 回放结束
          setIsPlaying(false);
          return replayData.kline_data.length - 1;
        }
        return newIndex;
      });

      // 更新进度
      const newProgress = Math.min(100, (currentIndex + 1) / replayData.kline_data.length * 100);
      setProgress(newProgress);

      lastUpdateTimeRef.current = timestamp;
    }

    animationFrameRef.current = requestAnimationFrame(animate);
  };

  /**
   * 监听当前索引变化，更新图表
   */
  useEffect(() => {
    if (!replayData) return;

    // 更新图表数据
    updateChartData(currentIndex);
    renderTradeSignals(currentIndex);

    // 更新进度
    const newProgress = (currentIndex / (replayData.kline_data.length - 1)) * 100;
    setProgress(newProgress);
  }, [currentIndex, replayData]);

  /**
   * 监听播放状态变化，启动或停止动画
   */
  useEffect(() => {
    if (isPlaying) {
      animationFrameRef.current = requestAnimationFrame(animate);
    } else if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, [isPlaying, speed]);

  /**
   * 监听回放数据变化，初始化图表
   */
  useEffect(() => {
    if (replayData && !loading) {
      initChart();
    }
  }, [replayData, loading]);

  /**
   * 组件挂载时加载回放数据
   */
  useEffect(() => {
    loadReplayData();
  }, [backtestId]);

  /**
   * 监听窗口大小变化，调整图表大小
   */
  useEffect(() => {
    const handleResize = () => {
      chartRef.current?.resize();
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  /**
   * 组件卸载时清理资源
   */
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      chartRef.current?.destroy();
    };
  }, []);

  return (
    <div className="backtest-replay-container">
      <h1>回测回放</h1>

      {loading ? (
        <div className="loading-container">
          <div className="loading">加载回放数据中...</div>
        </div>
      ) : error ? (
        <div className="error-container">
          <div className="error">{error}</div>
          <button className="btn btn-primary" onClick={loadReplayData}>
            重试
          </button>
        </div>
      ) : replayData ? (
        <>
          {/* 图表区域 */}
          <div className="chart-container">
            <div ref={chartContainerRef} className="chart"></div>
          </div>

          {/* 回放控制面板 */}
          <div className="replay-controls">
            {/* 播放控制按钮 */}
            <div className="control-buttons">
              <button 
                className="btn btn-secondary" 
                onClick={stopReplay}
                title="停止"
              >
                ⏹️ 停止
              </button>
              {isPlaying ? (
                <button 
                  className="btn btn-primary" 
                  onClick={pauseReplay}
                  title="暂停"
                >
                  ⏸️ 暂停
                </button>
              ) : (
                <button 
                  className="btn btn-primary" 
                  onClick={playReplay}
                  title="播放"
                >
                  ▶️ 播放
                </button>
              )}
            </div>

            {/* 进度条 */}
            <div className="progress-control">
              <input
                type="range"
                min="0"
                max="100"
                value={progress}
                onChange={(e) => adjustProgress(parseFloat(e.target.value))}
                className="progress-bar"
              />
              <div className="progress-info">
                <span className="progress-text">
                  {currentIndex + 1} / {replayData.kline_data.length}
                </span>
                <span className="progress-percentage">
                  {Math.round(progress)}%
                </span>
              </div>
            </div>

            {/* 速度控制 */}
            <div className="speed-control">
              <span className="speed-label">速度:</span>
              <div className="speed-buttons">
                {[0.5, 1, 2, 5, 10].map((speedOption) => (
                  <button
                    key={speedOption}
                    className={`btn ${speed === speedOption ? 'btn-primary active' : 'btn-secondary'}`}
                    onClick={() => adjustSpeed(speedOption)}
                  >
                    {speedOption}x
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* 回放信息 */}
          <div className="replay-info">
            <div className="info-item">
              <span className="label">当前进度:</span>
              <span className="value">{Math.round(progress)}%</span>
            </div>
            <div className="info-item">
              <span className="label">当前K线:</span>
              <span className="value">{currentIndex + 1} / {replayData.kline_data.length}</span>
            </div>
            <div className="info-item">
              <span className="label">播放速度:</span>
              <span className="value">{speed}x</span>
            </div>
            <div className="info-item">
              <span className="label">交易信号数量:</span>
              <span className="value">{replayData.trade_signals.length}</span>
            </div>
          </div>
        </>
      ) : (
        <div className="empty-container">
          <div className="empty">暂无回放数据</div>
        </div>
      )}
    </div>
  );
};

export default BacktestReplay;