import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// 从根目录 i18n 文件导入翻译
// 注意：这些文件通过构建脚本或符号链接同步到前端
import zhCN from '../../../i18n/zh-CN.json';
import enUS from '../../../i18n/en-US.json';

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
