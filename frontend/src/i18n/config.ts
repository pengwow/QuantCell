import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// 中文翻译
const zhCN = {
  chart: '图表分析',
  strategy_management: '策略管理',
  agent: '智能体',
  strategy_backtest: '策略回测',
  data_management: '数据管理',
  data_pool_management: '数据池管理',
  data_collection: '数据采集',
  data_quality: '数据质量',
  setting: '设置',
  system_status: '系统状态',
  connection: '连接状态',
  connected: '已连接',
  disconnected: '未连接',
  cpu_usage: 'CPU使用率',
  memory_usage: '内存使用',
  disk_space: '磁盘空间',
  welcome: '欢迎使用 QuantCell',
  page_not_found: '页面未找到',
  user: '用户',
  logout: '退出登录',
  help: '帮助',
  theme: {
    light: '浅色模式',
    dark: '深色模式',
    system: '跟随系统',
  },
};

// 英文翻译
const enUS = {
  chart: 'Chart Analysis',
  strategy_management: 'Strategy Management',
  agent: 'Agent',
  strategy_backtest: 'Strategy Backtest',
  data_management: 'Data Management',
  data_pool_management: 'Data Pool Management',
  data_collection: 'Data Collection',
  data_quality: 'Data Quality',
  setting: 'Settings',
  system_status: 'System Status',
  connection: 'Connection',
  connected: 'Connected',
  disconnected: 'Disconnected',
  cpu_usage: 'CPU Usage',
  memory_usage: 'Memory Usage',
  disk_space: 'Disk Space',
  welcome: 'Welcome to QuantCell',
  page_not_found: 'Page Not Found',
  user: 'User',
  logout: 'Logout',
  help: 'Help',
  theme: {
    light: 'Light Mode',
    dark: 'Dark Mode',
    system: 'System',
  },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      'zh-CN': { translation: zhCN },
      'en-US': { translation: enUS },
      'en': { translation: enUS },
      'zh': { translation: zhCN },
    },
    fallbackLng: 'zh-CN',
    debug: false,
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
