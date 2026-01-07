import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// 导入语言文件 - 使用统一的国际化目录
import zhCN from '@i18n/zh-CN.json';
import enUS from '@i18n/en-US.json';

// 定义支持的语言
const supportedLngs = ['zh-CN', 'en-US'];

// 初始化i18n
i18n
  // 添加语言检测器
  .use(LanguageDetector)
  // 添加React i18next插件
  .use(initReactI18next)
  // 配置i18n
  .init({
    // 资源文件
    resources: {
      'zh-CN': {
        translation: zhCN
      },
      'en-US': {
        translation: enUS
      }
    },
    // 支持的语言
    supportedLngs,
    // 默认语言
    fallbackLng: 'zh-CN',
    // 调试模式
    debug: false,
    // 插值配置
    interpolation: {
      escapeValue: false, // React已经处理了XSS
    },
    // 语言检测器配置
    detection: {
      // 顺序：先使用浏览器默认检测器
      order: ['navigator'],
      // 缓存配置
      caches: []
    },
  });

export default i18n;
