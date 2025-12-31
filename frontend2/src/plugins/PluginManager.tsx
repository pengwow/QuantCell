import { PluginBase } from './PluginBase';
import type { MenuGroup, RouteConfig } from './PluginBase';

// 插件类型定义
export interface Plugin {
  name: string;
  instance: PluginBase;
}

export class PluginManager {
  private static instance: PluginManager;
  private plugins: Map<string, Plugin> = new Map();
  private isInitialized: boolean = false;

  private constructor() {}

  /**
   * 获取插件管理器单例实例
   * @returns 插件管理器实例
   */
  public static getInstance(): PluginManager {
    if (!PluginManager.instance) {
      PluginManager.instance = new PluginManager();
    }
    return PluginManager.instance;
  }

  /**
   * 初始化插件管理器
   */
  public async init(): Promise<void> {
    if (this.isInitialized) {
      return;
    }

    await this.loadPlugins();
    this.startAllPlugins();
    this.isInitialized = true;
  }

  /**
   * 加载所有插件
   */
  private async loadPlugins(): Promise<void> {
    try {
      // 获取插件目录下的所有子目录
      const pluginDirs = await this.getPluginDirectories();
      
      for (const pluginDir of pluginDirs) {
        await this.loadPlugin(pluginDir);
      }

      console.log(`成功加载 ${this.plugins.size} 个插件`);
    } catch (error) {
      console.error('加载插件失败:', error);
    }
  }

  /**
   * 获取插件目录列表
   */
  private async getPluginDirectories(): Promise<string[]> {
    // 在Vite中，使用import.meta.glob获取目录列表
    const pluginDirs: string[] = [];
    
    // 动态导入所有插件目录下的index.tsx文件
    const pluginImports = import.meta.glob('./**/index.tsx', { eager: true });
    
    for (const path in pluginImports) {
      // 提取插件目录名称，支持连字符
      const match = path.match(/\.\/([\w-]+)\/index\.tsx$/);
      if (match && match[1]) {
        pluginDirs.push(match[1]);
      }
    }
    
    return pluginDirs;
  }

  /**
   * 加载指定插件
   * @param pluginName 插件名称
   */
  private async loadPlugin(pluginName: string): Promise<void> {
    try {
      // 动态导入插件
      const pluginModule = await import(`./${pluginName}/index.tsx`);
      
      // 检查插件模块是否有registerPlugin函数
      if (pluginModule && typeof pluginModule.registerPlugin === 'function') {
        // 创建插件实例
        const pluginInstance = pluginModule.registerPlugin();
        
        if (pluginInstance instanceof PluginBase) {
          // 注册插件
          pluginInstance.register();
          
          // 存储插件实例
          this.plugins.set(pluginName, {
            name: pluginName,
            instance: pluginInstance
          });
          
          console.log(`插件 ${pluginName} 加载成功`);
        } else {
          console.error(`插件 ${pluginName} 不是 PluginBase 的实例`);
        }
      } else {
        console.error(`插件 ${pluginName} 没有 registerPlugin 函数`);
      }
    } catch (error) {
      console.error(`加载插件 ${pluginName} 失败:`, error);
    }
  }

  /**
   * 启动所有插件
   */
  private startAllPlugins(): void {
    for (const plugin of this.plugins.values()) {
      plugin.instance.start();
    }
  }

  /**
   * 停止所有插件
   */
  public stopAllPlugins(): void {
    for (const plugin of this.plugins.values()) {
      plugin.instance.stop();
    }
  }

  /**
   * 获取所有插件
   * @returns 插件映射
   */
  public getPlugins(): Map<string, Plugin> {
    return this.plugins;
  }

  /**
   * 获取指定插件
   * @param pluginName 插件名称
   * @returns 插件实例，不存在返回undefined
   */
  public getPlugin(pluginName: string): Plugin | undefined {
    return this.plugins.get(pluginName);
  }

  /**
   * 获取所有插件的菜单
   * @returns 菜单数组
   */
  public getAllMenus(): MenuGroup[] {
    const allMenus: MenuGroup[] = [];
    
    for (const plugin of this.plugins.values()) {
      const menus = plugin.instance.getMenus();
      if (menus && menus.length > 0) {
        allMenus.push(...menus);
      }
    }
    
    return allMenus;
  }

  /**
   * 获取所有插件的路由
   * @returns 路由数组
   */
  public getAllRoutes(): RouteConfig[] {
    const allRoutes: RouteConfig[] = [];
    
    for (const plugin of this.plugins.values()) {
      const routes = plugin.instance.getRoutes();
      if (routes && routes.length > 0) {
        allRoutes.push(...routes);
      }
    }
    
    return allRoutes;
  }
}

// 导出插件管理器实例
export const pluginManager = PluginManager.getInstance();
