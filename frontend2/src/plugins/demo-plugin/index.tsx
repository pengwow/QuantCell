import { PluginBase } from '../PluginBase';
import { DemoPage } from './components/DemoPage';

export class DemoPlugin extends PluginBase {
  constructor() {
    super(
      'demo-plugin', 
      '1.0.0', 
      '前端插件demo', 
      'QBot Team'
    );
  }

  /**
   * 注册插件，添加菜单和路由
   */
  public register(): void {
    super.register();
    
    // 添加菜单
    this.addMenu({
      group: 'Demo插件',
      items: [
        {
          path: '/plugins/demo',
          name: 'Demo页面',
          icon: undefined // 使用默认图标
        }
      ]
    });
    
    // 添加路由
    this.addRoute({
      path: '/plugins/demo',
      element: <DemoPage />
    });
  }

  /**
   * 启动插件
   */
  public start(): void {
    super.start();
    console.log('Demo插件启动成功');
  }

  /**
   * 停止插件
   */
  public stop(): void {
    super.stop();
    console.log('Demo插件停止成功');
  }
}

/**
 * 插件注册入口，供插件管理器调用
 * @returns 插件实例
 */
export function registerPlugin(): DemoPlugin {
  return new DemoPlugin();
}
