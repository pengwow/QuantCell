import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import ChartIcon from './ChartIcon';
import ChartSettingModal from './ChartSettingModal';
import ChartTimezoneModal from './ChartTimezoneModal';
import ChartScreenshotModal from './ChartScreenshotModal';
import TokenDisplay from '../TokenDisplay';
import IndicatorSelectorModal from '../IndicatorSelectorModal';
import type { Indicator, ActiveIndicator } from '../../hooks/useIndicators';

export interface ChartPeriodItem {
  label: string;
  value: string;
}

interface ChartPeriodBarProps {
  /** 绘图栏是否展开（false 时菜单图标旋转 180°） */
  spread: boolean;
  onToggleSpread: () => void;
  symbol: { code: string; name?: string; base?: string };
  periods: ChartPeriodItem[];
  currentPeriod: string;
  onChangePeriod: (value: string) => void;
  activeIndicators: ActiveIndicator[];
  onToggleIndicator: (indicator: Indicator, params?: Record<string, unknown>) => void;
  /** QuantCell 特有的实时行情开关，由 ChartPage 传入，放在工具栏最右 */
  realtimeSlot?: React.ReactNode;
  onOpenSymbolSearch: () => void;
  currentTimezone: string;
  onTimezoneSelect: (timezone: string) => void;
  getSettings: () => Record<string, unknown>;
  onSettingChange: (path: string, value: unknown) => void;
  onRestoreDefaultSettings: () => void;
  /** 截图：由 ChartPage 调用 getConvertPictureUrl 生成 dataURL */
  getScreenshotUrl: () => string;
  /** 全屏目标元素（含工具栏与图表的主体容器） */
  fullscreenTarget: React.RefObject<HTMLElement | null>;
}

/**
 * 图表上方工具栏：复刻 klinecharts-pro 的 period-bar
 * 折叠菜单 + 品种 + 周期 + 指标/时区/设置/截图/全屏，最右接 QuantCell 的实时开关。
 * 本组件不直接持有图表实例，全部通过回调交给 ChartPage 执行。
 */
const ChartPeriodBar: React.FC<ChartPeriodBarProps> = ({
  spread,
  onToggleSpread,
  symbol,
  periods,
  currentPeriod,
  onChangePeriod,
  activeIndicators,
  onToggleIndicator,
  realtimeSlot,
  onOpenSymbolSearch,
  currentTimezone,
  onTimezoneSelect,
  getSettings,
  onSettingChange,
  onRestoreDefaultSettings,
  getScreenshotUrl,
  fullscreenTarget,
}) => {
  const { t } = useTranslation();

  const [indicatorVisible, setIndicatorVisible] = useState(false);
  const [settingVisible, setSettingVisible] = useState(false);
  const [timezoneVisible, setTimezoneVisible] = useState(false);
  const [screenshotVisible, setScreenshotVisible] = useState(false);
  const [screenshotUrl, setScreenshotUrl] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void fullscreenTarget.current?.requestFullscreen();
    }
  }, [fullscreenTarget]);

  // 截图 URL 在打开弹窗时即时生成，避免图表变动后预览过期
  const handleScreenshotClick = useCallback(() => {
    setScreenshotUrl(getScreenshotUrl());
    setScreenshotVisible(true);
  }, [getScreenshotUrl]);

  return (
    <>
      <div className="chart-period-bar">
        <div className="menu-container" onClick={onToggleSpread}>
          <ChartIcon name="menu" className={`menu-icon${spread ? '' : ' rotate'}`} />
        </div>

        <div className="symbol" onClick={onOpenSymbolSearch}>
          <TokenDisplay symbol={symbol.base || 'BTC'} size={20} style={{ marginRight: 6 }} />
          <span>{symbol.name || symbol.code}</span>
        </div>

        {periods.map((period) => (
          <span
            key={period.value}
            className={`item period${period.value === currentPeriod ? ' selected' : ''}`}
            onClick={() => onChangePeriod(period.value)}
          >
            {period.label}
          </span>
        ))}

        <div className="item tools first" onClick={() => setIndicatorVisible(true)}>
          <ChartIcon name="indicator" className="tool-ico" />
          <span>{t('chart.toolbar.indicator', '指标')}</span>
        </div>
        <div className="item tools" onClick={() => setTimezoneVisible(true)}>
          <ChartIcon name="timezone" className="tool-ico" />
          <span>{t('chart.toolbar.timezone', '时区')}</span>
        </div>
        <div className="item tools" onClick={() => setSettingVisible(true)}>
          <ChartIcon name="setting" className="tool-ico" />
          <span>{t('chart.toolbar.setting', '设置')}</span>
        </div>
        <div className="item tools" onClick={handleScreenshotClick}>
          <ChartIcon name="screenshot" className="tool-ico" />
          <span>{t('chart.toolbar.screenshot', '截图')}</span>
        </div>
        <div className="item tools" onClick={toggleFullscreen}>
          <ChartIcon name={isFullscreen ? 'exit-full-screen' : 'full-screen'} className="tool-ico" />
          <span>
            {isFullscreen
              ? t('chart.toolbar.exitFullscreen', '退出全屏')
              : t('chart.toolbar.fullscreen', '全屏')}
          </span>
        </div>

        {realtimeSlot ? <div className="live-area">{realtimeSlot}</div> : null}
      </div>

      <IndicatorSelectorModal
        visible={indicatorVisible}
        onClose={() => setIndicatorVisible(false)}
        activeIndicators={activeIndicators}
        onToggleIndicator={onToggleIndicator}
      />
      <ChartSettingModal
        open={settingVisible}
        onClose={() => setSettingVisible(false)}
        getSettings={getSettings}
        onChange={onSettingChange}
        onRestoreDefault={onRestoreDefaultSettings}
      />
      <ChartTimezoneModal
        open={timezoneVisible}
        onClose={() => setTimezoneVisible(false)}
        current={currentTimezone}
        onSelect={onTimezoneSelect}
      />
      <ChartScreenshotModal
        open={screenshotVisible}
        onClose={() => setScreenshotVisible(false)}
        url={screenshotUrl}
      />
    </>
  );
};

export default ChartPeriodBar;
