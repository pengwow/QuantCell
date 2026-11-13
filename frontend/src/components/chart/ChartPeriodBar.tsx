import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BellOutlined } from '@ant-design/icons';
import ChartIcon from './ChartIcon';
import ChartSettingModal from './ChartSettingModal';
import ChartTimezoneModal from './ChartTimezoneModal';
import ChartScreenshotModal from './ChartScreenshotModal';
import TokenDisplay from '../TokenDisplay';
import IndicatorSelectorModal from '../IndicatorSelectorModal';
import IndicatorAlertsModal from '../IndicatorAlertsModal';
import type { Indicator, ActiveIndicator } from '../../hooks/useIndicators';

export interface ChartPeriodItem {
  label: string;
  value: string;
}

interface ChartPeriodBarProps {
  /** 绘图栏是否展开（false 时菜单图标旋转 180°） */
  spread: boolean;
  /** 不传则隐藏收起按钮，左侧绘图栏常驻（回放页使用） */
  onToggleSpread?: () => void;
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
  /** 指标范围：all = 内置 + 自定义；builtin-local = 只展示内置指标（行情回放页） */
  indicatorScope?: 'all' | 'builtin-local';
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
  indicatorScope = 'all',
}) => {
  const { t } = useTranslation();

  const [indicatorVisible, setIndicatorVisible] = useState(false);
  const [alertsVisible, setAlertsVisible] = useState(false);
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
        {onToggleSpread && (
          <div className="menu-container" onClick={onToggleSpread}>
            <ChartIcon name="menu" className={`menu-icon${spread ? '' : ' rotate'}`} />
          </div>
        )}

        <div className="symbol" onClick={onOpenSymbolSearch}>
          <TokenDisplay symbol={symbol.base || 'BTC'} size={20} style={{ marginRight: 6 }} />
          <span>{symbol.name || symbol.code}</span>
        </div>

        {/* 周期条独立成滑动容器：窄屏时 overflow-x 横滑，避免整条工具栏溢出屏幕 */}
        <div className="period-strip">
          {periods.map((period) => (
            <span
              key={period.value}
              className={`item period${period.value === currentPeriod ? ' selected' : ''}`}
              onClick={() => onChangePeriod(period.value)}
            >
              {period.label}
            </span>
          ))}
        </div>

        <div className="item tools first" title={t('chart.toolbar.indicator')} onClick={() => setIndicatorVisible(true)}>
          <ChartIcon name="indicator" className="tool-ico" />
          <span className="tool-label">{t('chart.toolbar.indicator')}</span>
        </div>
        {/* 信号提醒直达入口：规则管理原本藏在编辑器提醒 Tab 三层深处；回放页（builtin-local）无自定义指标，隐藏 */}
        {indicatorScope !== 'builtin-local' && (
          <div className="item tools" title={t('chart.toolbar.alerts')} onClick={() => setAlertsVisible(true)}>
            {/* 不用 .tool-ico（CSS mask 方案），antd 字体图标直接继承文字色即可与图表图标对齐 */}
            <BellOutlined style={{ fontSize: 16, marginRight: 4 }} />
            <span className="tool-label">{t('chart.toolbar.alerts')}</span>
          </div>
        )}
        <div className="item tools" title={t('chart.toolbar.timezone')} onClick={() => setTimezoneVisible(true)}>
          <ChartIcon name="timezone" className="tool-ico" />
          <span className="tool-label">{t('chart.toolbar.timezone')}</span>
        </div>
        <div className="item tools" title={t('chart.toolbar.setting')} onClick={() => setSettingVisible(true)}>
          <ChartIcon name="setting" className="tool-ico" />
          <span className="tool-label">{t('chart.toolbar.setting')}</span>
        </div>
        <div className="item tools" title={t('chart.toolbar.screenshot')} onClick={handleScreenshotClick}>
          <ChartIcon name="screenshot" className="tool-ico" />
          <span className="tool-label">{t('chart.toolbar.screenshot')}</span>
        </div>
        <div
          className="item tools"
          title={isFullscreen
            ? t('chart.toolbar.exitFullscreen')
            : t('chart.toolbar.fullscreen')}
          onClick={toggleFullscreen}
        >
          <ChartIcon name={isFullscreen ? 'exit-full-screen' : 'full-screen'} className="tool-ico" />
          <span className="tool-label">
            {isFullscreen
              ? t('chart.toolbar.exitFullscreen')
              : t('chart.toolbar.fullscreen')}
          </span>
        </div>

        {realtimeSlot ? <div className="live-area">{realtimeSlot}</div> : null}
      </div>

      <IndicatorSelectorModal
        visible={indicatorVisible}
        onClose={() => setIndicatorVisible(false)}
        activeIndicators={activeIndicators}
        onToggleIndicator={onToggleIndicator}
        scope={indicatorScope}
      />
      <IndicatorAlertsModal
        visible={alertsVisible}
        onClose={() => setAlertsVisible(false)}
        // 新建提醒规则的表单默认值对齐图表当前交易对与周期
        defaultSymbol={symbol.code}
        defaultPeriod={currentPeriod}
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
