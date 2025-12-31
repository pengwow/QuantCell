import { configApi } from '../api';

/**
 * 配置加载器
 * 功能：从API获取配置数据，并提供全局访问方式
 */

// 定义配置对象类型 - 直接使用键值对格式，与后端返回格式保持一致
export interface AppConfig {
  [key: string]: any;
}

/**
 * 加载配置数据
 * @returns 配置数据对象
 */
export const loadConfig = async (): Promise<AppConfig> => {
  try {
    console.log('ConfigLoader: 开始加载配置数据');
    const configData = await configApi.getConfig();
    console.log('ConfigLoader: 配置数据加载成功:', configData);
    
    // 直接返回配置数据，不进行额外转换，保持与后端一致
    let formattedConfig: AppConfig = {};
    
    if (Array.isArray(configData)) {
      // 如果返回的是数组形式，转换为直接键值对
      configData.forEach(item => {
        formattedConfig[item.key] = item.value;
      });
    } else {
      // 如果返回的是对象形式，直接使用
      formattedConfig = configData;
    }
    
    return formattedConfig;
  } catch (error) {
    console.error('ConfigLoader: 配置数据加载失败:', error);
    // 返回空配置对象，确保应用能正常启动
    return {};
  }
};

/**
 * 更新配置数据
 * @param configData 新的配置数据
 */
export const updateConfig = (configData: AppConfig): void => {
  // 更新全局配置
  if (typeof window !== 'undefined') {
    (window as any).APP_CONFIG = configData;
    console.log('ConfigLoader: 全局配置已更新:', configData);
  }
};
