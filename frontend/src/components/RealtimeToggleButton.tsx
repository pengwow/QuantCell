/**
 * 实时数据控制按钮组件
 *
 * 功能：
 * - 控制实时数据更新的开启与暂停
 * - 显示播放/暂停图标
 * - 鼠标悬停显示功能提示
 * - 管理实时数据状态
 * - 订阅/取消订阅WebSocket K线数据
 */

import { useState, useEffect, useCallback } from 'react';
import { Button, Tooltip, message } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import * as realtimeApi from '../api/realtimeApi';
import { wsService } from '../services/websocketService';

interface RealtimeToggleButtonProps {
  /** 当前交易对，如 BTCUSDT */
  symbol: string;
  /** 当前时间周期，如 1m, 5m, 15m */
  period: string;
  /** 系统默认实时数据状态 */
  defaultRealtimeEnabled?: boolean;
  /** 实时数据更新回调 */
  onRealtimeData?: (data: any) => void;
  /** 状态变化回调 */
  onStatusChange?: (isRealtime: boolean) => void;
}

// localStorage key for realtime state
const REALTIME_STATE_KEY = 'realtime_button_state';

interface RealtimeState {
  isRealtime: boolean;
  symbol: string;
  period: string;
  timestamp: number;
}

export function RealtimeToggleButton({
  symbol,
  period,
  defaultRealtimeEnabled = false,
  onRealtimeData,
  onStatusChange,
}: RealtimeToggleButtonProps) {
  // 从 localStorage 恢复状态
  const getInitialState = (): boolean => {
    try {
      const savedState = localStorage.getItem(REALTIME_STATE_KEY);
      if (savedState) {
        const state: RealtimeState = JSON.parse(savedState);
        // 检查状态是否在5分钟内（避免过期状态）
        const isRecent = Date.now() - state.timestamp < 5 * 60 * 1000;
        // 检查是否是相同的交易对和周期
        const isSameSymbol = state.symbol === symbol;
        const isSamePeriod = state.period === period;

        if (isRecent && isSameSymbol && isSamePeriod && state.isRealtime) {
          console.log('[RealtimeToggleButton] 从localStorage恢复实时状态');
          return true;
        }
      }
    } catch (e) {
      console.error('[RealtimeToggleButton] 恢复状态失败:', e);
    }
    return defaultRealtimeEnabled;
  };

  // 实时数据状态
  const [isRealtime, setIsRealtime] = useState(getInitialState);
  // 加载状态
  const [loading, setLoading] = useState(false);
  // 是否已订阅
  const [isSubscribed, setIsSubscribed] = useState(false);
  // 是否已经恢复过连接
  const [hasRestored, setHasRestored] = useState(false);
  // 操作锁，防止快速点击
  const [isProcessing, setIsProcessing] = useState(false);

  // 构建K线频道名称
  const klineChannel = `${symbol}@kline_${period}`;

  // 保存状态到 localStorage
  const saveState = (realtime: boolean) => {
    try {
      const state: RealtimeState = {
        isRealtime: realtime,
        symbol,
        period,
        timestamp: Date.now(),
      };
      localStorage.setItem(REALTIME_STATE_KEY, JSON.stringify(state));
    } catch (e) {
      console.error('[RealtimeToggleButton] 保存状态失败:', e);
    }
  };

  /**
   * 处理WebSocket消息
   */
  const handleWebSocketMessage = useCallback((data: any) => {
    console.log('[RealtimeToggleButton] 收到WebSocket消息:', data);
    if (data && onRealtimeData) {
      console.log('[RealtimeToggleButton] 调用onRealtimeData回调');
      onRealtimeData(data);
    } else {
      console.warn('[RealtimeToggleButton] 数据或回调为空:', { data, hasCallback: !!onRealtimeData });
    }
  }, [onRealtimeData]);

  /**
   * 启动实时数据更新
   */
  const startRealtime = async (silent: boolean = false) => {
    setLoading(true);
    try {
      console.log('[RealtimeToggleButton] 启动实时数据...');

      // 0. 确保WebSocket连接并订阅kline主题
      console.log('[RealtimeToggleButton] 确保WebSocket连接...');
      if (!wsService.getConnected()) {
        console.log('[RealtimeToggleButton] WebSocket未连接，正在连接...');
        wsService.connect();
        // 等待连接建立
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      // 订阅kline主题
      console.log('[RealtimeToggleButton] 订阅kline主题...');
      wsService.subscribe('kline');

      // 1. 先检查实时引擎状态
      console.log('[RealtimeToggleButton] 检查引擎状态...');
      const status = await realtimeApi.getRealtimeStatus();
      console.log('[RealtimeToggleButton] 引擎状态:', status);

      // 2. 如果引擎未运行，快速启动引擎（不连接交易所）
      if (status.status !== 'running') {
        console.log('[RealtimeToggleButton] 引擎未运行，快速启动引擎...');
        const startResult = await realtimeApi.startRealtimeEngine();
        console.log('[RealtimeToggleButton] 启动结果:', startResult);

        if (!startResult.success) {
          if (!silent) message.error('启动实时引擎失败');
          return;
        }
      } else {
        console.log('[RealtimeToggleButton] 引擎已在运行');
      }

      // 3. 连接交易所（如果未连接）
      if (!status.connected) {
        console.log('[RealtimeToggleButton] 连接交易所...');
        const connectResult = await realtimeApi.connectExchange();
        console.log('[RealtimeToggleButton] 连接结果:', connectResult);

        if (!connectResult.success) {
          if (!silent) message.error('连接交易所失败');
          return;
        }
      } else {
        console.log('[RealtimeToggleButton] 交易所已连接');
      }

      // 4. 订阅K线数据频道
      console.log('[RealtimeToggleButton] 订阅K线频道:', klineChannel);
      const subscribeResult = await realtimeApi.subscribeKlineChannels([klineChannel]);
      console.log('[RealtimeToggleButton] 订阅结果:', subscribeResult);

      if (!subscribeResult.success) {
        if (!silent) message.error(`订阅K线数据失败`);
        return;
      }

      // 5. 订阅WebSocket消息（先注册监听器）
      console.log('[RealtimeToggleButton] 订阅WebSocket消息...');
      // 只订阅 'kline' 主题，避免重复处理
      wsService.on('kline', handleWebSocketMessage);
      // 检查是否已注册监听器
      console.log('[RealtimeToggleButton] WebSocket监听器已注册');

      // 6. 更新状态
      setIsRealtime(true);
      setIsSubscribed(true);
      saveState(true); // 保存状态到 localStorage

      // 只在非静默模式下显示提示
      if (!silent) {
        message.success('实时数据更新已开启');
      }

      // 7. 通知父组件
      if (onStatusChange) {
        onStatusChange(true);
      }
    } catch (error: any) {
      console.error('[RealtimeToggleButton] 启动实时数据失败:', error);
      if (!silent) {
        message.error(`启动实时数据失败: ${error.message || '请检查网络连接'}`);
      }
    } finally {
      setLoading(false);
    }
  };

  /**
   * 停止实时数据更新
   */
  const stopRealtime = async () => {
    setLoading(true);
    try {
      console.log('[RealtimeToggleButton] 停止实时数据...');

      // 1. 取消订阅K线数据频道
      if (isSubscribed) {
        console.log('[RealtimeToggleButton] 取消订阅K线频道:', klineChannel);
        const unsubscribeResult = await realtimeApi.unsubscribeKlineChannels([klineChannel]);
        console.log('[RealtimeToggleButton] 取消订阅结果:', unsubscribeResult);
      }

      // 2. 移除WebSocket监听器
      console.log('[RealtimeToggleButton] 移除WebSocket监听器...');
      wsService.off('kline', handleWebSocketMessage);
      wsService.off('kline:update', handleWebSocketMessage);

      // 3. 断开交易所连接（可选，根据需求决定是否断开）
      // 如果希望保持连接以便快速恢复，可以注释掉下面这行
      // await realtimeApi.disconnectExchange();

      // 4. 更新状态
      setIsRealtime(false);
      setIsSubscribed(false);
      saveState(false); // 保存状态到 localStorage
      message.success('实时数据更新已暂停');

      // 5. 通知父组件
      if (onStatusChange) {
        onStatusChange(false);
      }
    } catch (error: any) {
      console.error('[RealtimeToggleButton] 停止实时数据失败:', error);
      message.error(`停止实时数据失败: ${error.message || '未知错误'}`);
    } finally {
      setLoading(false);
    }
  };

  /**
   * 切换实时数据状态
   */
  const toggleRealtime = async () => {
    // 防止快速点击，如果正在处理中则忽略
    if (isProcessing || loading) {
      console.log('[RealtimeToggleButton] 操作过于频繁，请稍后再试');
      return;
    }

    setIsProcessing(true);
    try {
      if (isRealtime) {
        await stopRealtime();
      } else {
        await startRealtime();
      }
    } finally {
      // 延迟释放锁，防止快速连续点击
      setTimeout(() => {
        setIsProcessing(false);
      }, 2000);
    }
  };

  /**
   * 获取按钮提示文本
   */
  const getTooltipText = () => {
    if (loading) {
      return isRealtime ? '正在暂停...' : '正在开启...';
    }
    return isRealtime ? '暂停实时更新' : '开启实时更新';
  };

  /**
   * 组件挂载时恢复连接状态
   */
  useEffect(() => {
    // 如果需要恢复实时连接（从localStorage恢复的状态）
    if (isRealtime && !hasRestored) {
      console.log('[RealtimeToggleButton] 检测到需要恢复实时连接...');
      setHasRestored(true);
      // 延迟恢复，等待组件完全挂载
      setTimeout(() => {
        startRealtime(true); // 传入 true 表示静默模式，不显示提示
      }, 500);
    }

    // 组件卸载时清理
    return () => {
      if (isSubscribed) {
        console.log('[RealtimeToggleButton] 组件卸载，清理订阅...');
        // 取消订阅但不停止引擎（避免影响其他页面）
        realtimeApi.unsubscribeKlineChannels([klineChannel]).catch(console.error);
        wsService.off('kline', handleWebSocketMessage);
        wsService.off('kline:update', handleWebSocketMessage);
      }
    };
  }, []);

  /**
   * 当交易对或周期变化时，重新订阅
   */
  useEffect(() => {
    if (isRealtime && isSubscribed) {
      console.log('[RealtimeToggleButton] 交易对/周期变化，重新订阅...');
      console.log('[RealtimeToggleButton] 旧频道:', klineChannel);

      // 先取消旧订阅
      realtimeApi.unsubscribeKlineChannels([klineChannel]).catch((error) => {
        console.error('[RealtimeToggleButton] 取消旧订阅失败:', error);
      });

      // 再订阅新频道
      const newChannel = `${symbol}@kline_${period}`;
      console.log('[RealtimeToggleButton] 新频道:', newChannel);

      realtimeApi.subscribeKlineChannels([newChannel]).then((result) => {
        console.log('[RealtimeToggleButton] 新订阅结果:', result);
      }).catch((error) => {
        console.error('[RealtimeToggleButton] 新订阅失败:', error);
      });
    }
  }, [symbol, period]);

  return (
    <Tooltip
      title={getTooltipText()}
      placement="left"
      getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
      mouseEnterDelay={0.5}
    >
      <Button
        type={isRealtime ? 'primary' : 'default'}
        icon={loading ? <LoadingOutlined /> : (isRealtime ? <PauseCircleOutlined /> : <PlayCircleOutlined />)}
        onClick={toggleRealtime}
        loading={loading}
        disabled={isProcessing}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '32px',
          height: '32px',
          padding: 0,
          borderRadius: '4px',
        }}
      />
    </Tooltip>
  );
}

export default RealtimeToggleButton;
