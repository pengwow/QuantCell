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
    this.setupHotReload(); // 启用热重载
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
    const pluginDirs: string[] = [];
    
    try {
      if (import.meta.env.DEV) {
        // 开发环境：使用import.meta.glob动态获取插件manifest
        const manifestImports = import.meta.glob('./**/manifest.json', { eager: true });
        
        for (const path in manifestImports) {
          // 提取插件目录名称，支持连字符
          const match = path.match(/\.\/([\w-]+)\/manifest\.json$/);
          if (match && match[1]) {
            pluginDirs.push(match[1]);
          }
        }
      } else {
        // 生产环境：从window.__QUANTCELL_PLUGINS__获取（在index.html中注入）
        const global = window as any;
        if (global.__QUANTCELL_PLUGINS__) {
          pluginDirs.push(...global.__QUANTCELL_PLUGINS__);
        }
      }
    } catch (error) {
      console.error('获取插件目录失败:', error);
    }
    
    return pluginDirs;
  }

  /**
   * 加载指定插件
   * @param pluginName 插件名称
   */
  private async loadPlugin(pluginName: string): Promise<void> {
    try {
      // 动态导入插件，Vite 开发环境会自动处理缓存
      console.log(`开始加载插件: ${pluginName}`);
      const pluginModule = await import(`./${pluginName}/index.tsx`);
      
      // 检查插件模块是否有registerPlugin函数
      if (pluginModule) {
        if (typeof pluginModule.registerPlugin === 'function') {
          // 创建插件实例
          const pluginInstance = pluginModule.registerPlugin();
          
          if (pluginInstance instanceof PluginBase) {
            // 如果插件已存在，先停止旧实例
            if (this.plugins.has(pluginName)) {
              const oldPlugin = this.plugins.get(pluginName)!;
              oldPlugin.instance.stop();
            }
            
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
          console.error(`插件模块导出:`, Object.keys(pluginModule));
        }
      } else {
        console.error(`插件 ${pluginName} 模块加载失败，返回值为 undefined`);
      }
    } catch (error) {
      console.error(`加载插件 ${pluginName} 失败:`);
      if (error instanceof Error) {
        console.error(`错误信息: ${error.message}`);
        console.error(`错误栈: ${error.stack}`);
      } else {
        console.error(`错误对象:`, error);
      }
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

  /**
   * 获取所有插件的系统配置
   * @returns 插件配置信息数组
   */
  public getAllPluginConfigs(): Array<{
    name: string;
    configs: any[];
    menuName: string;
  }> {
    const allConfigs: Array<{
      name: string;
      configs: any[];
      menuName: string;
    }> = [];
    
    for (const plugin of this.plugins.values()) {
      const configs = plugin.instance.getSystemConfigs();
      const menuName = plugin.instance.getConfigMenuName();
      if (configs && configs.length > 0) {
        allConfigs.push({
          name: plugin.name,
          configs,
          menuName: menuName || `${plugin.name} 设置`
        });
      }
    }
    
    return allConfigs;
  }

  /**
   * 刷新指定插件
   * @param pluginName 插件名称
   */
  public async reloadPlugin(pluginName: string): Promise<void> {
    console.log(`开始刷新插件 ${pluginName}`);
    await this.loadPlugin(pluginName);
    console.log(`插件 ${pluginName} 刷新成功`);
  }

  /**
   * 刷新所有插件
   */
  public async reloadAllPlugins(): Promise<void> {
    console.log('开始刷新所有插件');
    const pluginNames = Array.from(this.plugins.keys());
    
    for (const pluginName of pluginNames) {
      await this.reloadPlugin(pluginName);
    }
    
    console.log('所有插件刷新成功');
  }

  /**
   * 安装新插件
   * @param pluginName 插件名称
   */
  public async installPlugin(pluginName: string): Promise<void> {
    console.log(`开始安装插件 ${pluginName}`);
    
    // 检查插件是否已存在
    if (this.plugins.has(pluginName)) {
      await this.reloadPlugin(pluginName);
    } else {
      await this.loadPlugin(pluginName);
    }
    
    console.log(`插件 ${pluginName} 安装成功`);
  }

  /**
   * 卸载插件
   * @param pluginName 插件名称
   */
  public async uninstallPlugin(pluginName: string): Promise<void> {
    console.log(`开始卸载插件 ${pluginName}`);
    
    const plugin = this.plugins.get(pluginName);
    if (plugin) {
      // 停止插件
      plugin.instance.stop();
      // 移除插件
      this.plugins.delete(pluginName);
      console.log(`插件 ${pluginName} 卸载成功`);
    }
  }

  /**
   * 设置热重载
   */
  public setupHotReload(): void {
    if (import.meta.env.DEV && import.meta.hot) {
      console.log('启用插件热重载');
      
      // 简化热重载逻辑：当任何文件变化时，重新加载所有插件
      import.meta.hot.on('vite:beforeUpdate', () => {
        // 这里简化处理，实际项目中可以根据变化的文件路径更精确地刷新插件
        this.reloadAllPlugins();
      });
    }
  }
}

// 导出插件管理器实例
export const pluginManager = PluginManager.getInstance();
