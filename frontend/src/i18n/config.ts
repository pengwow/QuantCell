import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// 从根目录 i18n 文件导入翻译
// 注意：这些文件通过构建脚本或符号链接同步到前端
import zhCN from '../../../i18n/zh-CN.json';
import enUS from '../../../i18n/en-US.json';

// 智能检测初始语言（优先级：localStorage > 浏览器检测 > 默认中文）
const getInitialLanguage = (): string => {
  // 1. 优先读取 localStorage（用户上次选择的语言）
  const savedLanguage = typeof window !== 'undefined'
    ? localStorage.getItem('quantcell-language')
    : null;

  if (savedLanguage && (savedLanguage === 'zh-CN' || savedLanguage === 'en-US')) {
    console.log(`[i18n] 使用 localStorage 中的语言设置: ${savedLanguage}`);
    return savedLanguage;
  }

  // 2. 回退到默认语言
  console.log('[i18n] 使用默认语言: zh-CN');
  return 'zh-CN';
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
    lng: getInitialLanguage(), // 使用智能检测的初始语言
    fallbackLng: 'zh-CN',
    debug: false,
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
