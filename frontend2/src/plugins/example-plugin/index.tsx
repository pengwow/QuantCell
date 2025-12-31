import { PluginBase } from '../PluginBase';
import { ExamplePage } from './components/ExamplePage';

export class ExamplePlugin extends PluginBase {
  constructor() {
    super(
      'example-plugin', 
      '1.0.0', 
      '示例前端插件', 
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
      group: '插件示例',
      items: [
        {
          path: '/plugins/example',
          name: '示例页面',
          icon: undefined // 使用默认图标
        }
      ]
    });
    
    // 添加路由
    this.addRoute({
      path: '/plugins/example',
      element: <ExamplePage />
    });
  }

  /**
   * 启动插件
   */
  public start(): void {
    super.start();
    console.log('示例插件启动成功');
  }

  /**
   * 停止插件
   */
  public stop(): void {
    super.stop();
    console.log('示例插件停止成功');
  }
}

/**
 * 插件注册入口，供插件管理器调用
 * @returns 插件实例
 */
export function registerPlugin(): ExamplePlugin {
  return new ExamplePlugin();
}
