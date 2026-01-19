import { PluginBase } from '../PluginBase';

/**
 * 测试插件
 * 功能：演示插件配置功能
 */
export class TestPlugin extends PluginBase {
  constructor() {
    super('test-plugin', '1.0.0', '测试插件，用于演示插件配置功能', '测试团队');
    
    // 设置配置菜单名称
    this.setConfigMenuName('测试插件设置');
    
    // 注册系统配置项
    this.addSystemConfig({
      key: 'test_plugin_enabled',
      value: 'true',
      description: '是否启用测试插件',
      type: 'boolean'
    });
    
    this.addSystemConfig({
      key: 'test_plugin_api_key',
      value: '',
      description: '测试插件 API Key',
      type: 'string'
    });
    
    this.addSystemConfig({
      key: 'test_plugin_mode',
      value: 'normal',
      description: '测试插件运行模式',
      type: 'select',
      options: ['normal', 'debug', 'verbose']
    });
    
    this.addSystemConfig({
      key: 'test_plugin_timeout',
      value: '30',
      description: '测试插件超时时间（秒）',
      type: 'number'
    });
  }
  
  /**
   * 启动插件
   */
  public start(): void {
    super.start();
    console.log('测试插件已启动');
  }
  
  /**
   * 停止插件
   */
  public stop(): void {
    super.stop();
    console.log('测试插件已停止');
  }
}

/**
 * 注册插件
 * @returns 插件实例
 */
export function registerPlugin(): PluginBase {
  return new TestPlugin();
}
