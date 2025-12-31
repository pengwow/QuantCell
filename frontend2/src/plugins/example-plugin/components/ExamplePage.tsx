import React from 'react';
import { Card, Button, Typography, Space } from 'antd';

const { Title, Paragraph, Text } = Typography;

/**
 * 示例插件页面组件
 */
export const ExamplePage: React.FC = () => {
  return (
    <div style={{ padding: '20px' }}>
      <Card title="示例插件页面" bordered={false}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div>
            <Title level={3}>插件功能演示</Title>
            <Paragraph>
              这是一个示例插件页面，展示了QBot插件系统的基本功能。
              插件系统允许开发者扩展系统功能，添加新的页面和菜单。
            </Paragraph>
          </div>
          
          <div>
            <Title level={4}>插件特性</Title>
            <ul>
              <li>动态加载插件</li>
              <li>扩展侧边栏菜单</li>
              <li>添加新的页面路由</li>
              <li>支持前后端插件</li>
              <li>插件生命周期管理</li>
            </ul>
          </div>
          
          <div style={{ display: 'flex', gap: '10px' }}>
            <Button type="primary">示例按钮1</Button>
            <Button>示例按钮2</Button>
            <Button danger>示例按钮3</Button>
          </div>
          
          <div>
            <Text strong>插件信息：</Text>
            <Text>名称：example-plugin</Text>
            <br />
            <Text>版本：1.0.0</Text>
            <br />
            <Text>作者：QBot Team</Text>
          </div>
        </Space>
      </Card>
    </div>
  );
};

export default ExamplePage;
