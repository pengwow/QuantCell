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
import { Button, Tooltip, App } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
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
  onRealtimeData?: (data: unknown) => void;
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
  const { message } = App.useApp();
  const { t } = useTranslation();
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
          console.log('[RealtimeToggleButton] Restored realtime state from localStorage');
          return true;
        }
      }
    } catch (e) {
      console.error('[RealtimeToggleButton] Failed to restore state:', e);
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
      console.error('[RealtimeToggleButton] Failed to save state:', e);
    }
  };

  /**
   * 处理WebSocket消息
   */
  const handleWebSocketMessage = useCallback((data: unknown) => {
    console.log('[RealtimeToggleButton] WebSocket message received:', data);
    if (data && onRealtimeData) {
      console.log('[RealtimeToggleButton] Calling onRealtimeData callback');
      onRealtimeData(data);
    } else {
      console.warn('[RealtimeToggleButton] Data or callback is empty:', { data, hasCallback: !!onRealtimeData });
    }
  }, [onRealtimeData]);

  /**
   * 启动实时数据更新
   */
  const startRealtime = async (silent: boolean = false) => {
    setLoading(true);
    try {
      console.log('[RealtimeToggleButton] Starting realtime data...');

      // 0. 确保WebSocket连接并订阅kline主题
      console.log('[RealtimeToggleButton] Ensuring WebSocket connection...');
      if (!wsService.getConnected()) {
        console.log('[RealtimeToggleButton] WebSocket not connected, connecting...');
        wsService.connect();
        // 等待连接建立
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      // 订阅kline主题
      console.log('[RealtimeToggleButton] Subscribing kline topic...');
      wsService.subscribe('kline');

      // 1. 先检查实时引擎状态
      console.log('[RealtimeToggleButton] Checking engine status...');
      const status = await realtimeApi.getRealtimeStatus();
      console.log('[RealtimeToggleButton] Engine status:', status);

      // 2. 如果引擎未运行，快速启动引擎（不连接交易所）
      if (status.status !== 'running') {
        console.log('[RealtimeToggleButton] Engine not running, starting engine quickly...');
        const startResult = await realtimeApi.startRealtimeEngine();
        console.log('[RealtimeToggleButton] Start result:', startResult);

        if (!startResult.success) {
          if (!silent) message.error(t('rtb_msg_start_engine_failed'));
          return;
        }
      } else {
        console.log('[RealtimeToggleButton] Engine already running');
      }

      // 3. 连接交易所（如果未连接）
      if (!status.connected) {
        console.log('[RealtimeToggleButton] Connecting exchange...');
        const connectResult = await realtimeApi.connectExchange();
        console.log('[RealtimeToggleButton] Connect result:', connectResult);

        if (!connectResult.success) {
          if (!silent) message.error(t('rtb_msg_connect_exchange_failed'));
          return;
        }
      } else {
        console.log('[RealtimeToggleButton] Exchange already connected');
      }

      // 4. 订阅K线数据频道
      console.log('[RealtimeToggleButton] Subscribing kline channels:', klineChannel);
      const subscribeResult = await realtimeApi.subscribeKlineChannels([klineChannel]);
      console.log('[RealtimeToggleButton] Subscribe result:', subscribeResult);

      if (!subscribeResult.success) {
        if (!silent) message.error(t('rtb_msg_subscribe_failed'));
        return;
      }

      // 5. 订阅WebSocket消息（先注册监听器）
      console.log('[RealtimeToggleButton] Subscribing WebSocket messages...');
      // 只订阅 'kline' 主题，避免重复处理
      wsService.on('kline', handleWebSocketMessage);
      // 检查是否已注册监听器
      console.log('[RealtimeToggleButton] WebSocket listener registered');

      // 6. 更新状态
      setIsRealtime(true);
      setIsSubscribed(true);
      saveState(true); // 保存状态到 localStorage

      // 只在非静默模式下显示提示
      if (!silent) {
        message.success(t('rtb_msg_started'));
      }

      // 7. 通知父组件
      if (onStatusChange) {
        onStatusChange(true);
      }
    } catch (error) {
      console.error('[RealtimeToggleButton] Failed to start realtime data:', error);
      if (!silent) {
        message.error(t('rtb_msg_start_failed', { msg: error instanceof Error ? error.message : t('rtb_msg_check_network') }));
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
      console.log('[RealtimeToggleButton] Stopping realtime data...');

      // 1. 取消订阅K线数据频道
      if (isSubscribed) {
        console.log('[RealtimeToggleButton] Unsubscribing kline channel:', klineChannel);
        const unsubscribeResult = await realtimeApi.unsubscribeKlineChannels([klineChannel]);
        console.log('[RealtimeToggleButton] Unsubscribe result:', unsubscribeResult);

        // 检查引擎状态，如果引擎未运行，更新按钮状态为未开启
        if (unsubscribeResult.engine_status && unsubscribeResult.engine_status !== 'running') {
          console.log('[RealtimeToggleButton] Engine not running, resetting button state');
          setIsRealtime(false);
          setIsSubscribed(false);
          saveState(false);

          // 移除WebSocket监听器
          wsService.off('kline', handleWebSocketMessage);
          wsService.off('kline:update', handleWebSocketMessage);

          message.info(t('rtb_msg_engine_stopped'));

          // 通知父组件
          if (onStatusChange) {
            onStatusChange(false);
          }
          return;
        }
      }

      // 2. 移除WebSocket监听器
      console.log('[RealtimeToggleButton] Removing WebSocket listeners...');
      wsService.off('kline', handleWebSocketMessage);
      wsService.off('kline:update', handleWebSocketMessage);

      // 3. 断开交易所连接（可选，根据需求决定是否断开）
      // 如果希望保持连接以便快速恢复，可以注释掉下面这行
      // await realtimeApi.disconnectExchange();

      // 4. 更新状态
      setIsRealtime(false);
      setIsSubscribed(false);
      saveState(false); // 保存状态到 localStorage
      message.success(t('rtb_msg_paused'));

      // 5. 通知父组件
      if (onStatusChange) {
        onStatusChange(false);
      }
    } catch (error) {
      console.error('[RealtimeToggleButton] Failed to stop realtime data:', error);
      message.error(t('rtb_msg_stop_failed', { msg: error instanceof Error ? error.message : t('unknown_error') }));
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
      console.log('[RealtimeToggleButton] Operation too frequent, please retry later');
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
      return isRealtime ? t('rtb_tip_pausing') : t('rtb_tip_starting');
    }
    return isRealtime ? t('rtb_tip_pause') : t('rtb_tip_start');
  };

  /**
   * 组件挂载时恢复连接状态
   */
  useEffect(() => {
    // 如果需要恢复实时连接（从localStorage恢复的状态）
    if (isRealtime && !hasRestored) {
      console.log('[RealtimeToggleButton] Detected pending realtime connection restore...');
      setHasRestored(true);
      // 延迟恢复，等待组件完全挂载
      setTimeout(() => {
        startRealtime(true); // 传入 true 表示静默模式，不显示提示
      }, 500);
    }

    // 组件卸载时清理
    return () => {
      if (isSubscribed) {
        console.log('[RealtimeToggleButton] Component unmounting, cleaning up subscription...');
        // 取消订阅但不停止引擎（避免影响其他页面）
        realtimeApi.unsubscribeKlineChannels([klineChannel]).catch(console.error);
        wsService.off('kline', handleWebSocketMessage);
        wsService.off('kline:update', handleWebSocketMessage);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, []);

  /**
   * 当交易对或周期变化时，重新订阅
   */
  useEffect(() => {
    if (isRealtime && isSubscribed) {
      console.log('[RealtimeToggleButton] Symbol/period changed, resubscribing...');
      console.log('[RealtimeToggleButton] Old channel:', klineChannel);

      // 先取消旧订阅
      realtimeApi.unsubscribeKlineChannels([klineChannel]).catch((error) => {
        console.error('[RealtimeToggleButton] Failed to unsubscribe old channel:', error);
      });

      // 再订阅新频道
      const newChannel = `${symbol}@kline_${period}`;
      console.log('[RealtimeToggleButton] New channel:', newChannel);

      realtimeApi.subscribeKlineChannels([newChannel]).then((result) => {
        console.log('[RealtimeToggleButton] New subscribe result:', result);
      }).catch((error) => {
        console.error('[RealtimeToggleButton] Failed to subscribe new channel:', error);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
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
