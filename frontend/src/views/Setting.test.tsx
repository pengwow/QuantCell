import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Setting } from './Setting';
import { configApi } from '../api';
import { pluginManager } from '../plugins/PluginManager';

// 模拟 API 调用
jest.mock('../api', () => ({
  configApi: {
    getPluginConfig: jest.fn(),
  },
}));

// 模拟插件管理器
jest.mock('../plugins/PluginManager', () => ({
  pluginManager: {
    getAllPluginConfigs: jest.fn(),
    getPlugin: jest.fn(),
  },
}));

// 模拟 window.APP_CONFIG
Object.defineProperty(window, 'APP_CONFIG', {
  writable: true,
  value: {},
});

describe('Setting Component - Plugin Config', () => {
  beforeEach(() => {
    // 重置模拟
    jest.clearAllMocks();
    
    // 模拟插件配置
    (pluginManager.getAllPluginConfigs as jest.Mock).mockReturnValue([
      {
        name: 'test-plugin',
        configs: [
          {
            key: 'test_plugin_enabled',
            value: 'true',
            description: '是否启用测试插件',
            type: 'boolean',
          },
          {
            key: 'test_plugin_api_key',
            value: '',
            description: '测试插件 API Key',
            type: 'string',
          },
          {
            key: 'test_plugin_mode',
            value: 'normal',
            description: '测试插件运行模式',
            type: 'select',
            options: ['normal', 'debug', 'verbose'],
          },
          {
            key: 'test_plugin_timeout',
            value: '30',
            description: '测试插件超时时间（秒）',
            type: 'number',
          },
        ],
        menuName: '测试插件设置',
      },
    ]);
    
    // 模拟插件实例
    (pluginManager.getPlugin as jest.Mock).mockReturnValue({
      instance: {
        setConfig: jest.fn(),
        getConfig: jest.fn((key) => {
          const configs: Record<string, any> = {
            test_plugin_enabled: 'true',
            test_plugin_api_key: 'test-api-key',
            test_plugin_mode: 'normal',
            test_plugin_timeout: '30',
          };
          return configs[key];
        }),
      },
    });
    
    // 模拟 API 响应
    (configApi.getPluginConfig as jest.Mock).mockResolvedValue({
      test_plugin_enabled: '1',
      test_plugin_api_key: 'kkk',
      test_plugin_mode: 'normal',
      test_plugin_timeout: '9',
    });
  });

  test('should load plugin config when switching to plugin tab', async () => {
    render(<Setting />);
    
    // 模拟切换到插件配置页面
    const pluginTab = screen.getByText('测试插件设置');
    fireEvent.click(pluginTab);
    
    // 等待 API 调用完成
    await waitFor(() => {
      expect(configApi.getPluginConfig).toHaveBeenCalledWith('test-plugin');
    });
    
    // 检查 API 调用是否成功
    expect(configApi.getPluginConfig).toHaveBeenCalledTimes(1);
  });
});