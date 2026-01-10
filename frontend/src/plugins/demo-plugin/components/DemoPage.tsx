import React from 'react';
import { Card, Button, Typography, Space, Alert } from 'antd';

const { Title, Paragraph, Text } = Typography;

/**
 * Demo插件页面组件
 */
export const DemoPage: React.FC = () => {
  return (
    <div style={{ padding: '20px' }}>
      <Card title="Demo插件页面" variant="borderless">
        <Space orientation="vertical" size="large" style={{ width: '100%' }}>
          <Alert
            message="欢迎使用Demo插件"
            description="这是一个前端插件demo，展示了QBot插件系统的基本功能。"
            type="success"
            showIcon
          />
          
          <div>
            <Title level={3}>插件功能演示</Title>
            <Paragraph>
              这个demo展示了如何创建一个前端插件，包括：
            </Paragraph>
            <ul>
              <li>动态添加侧边栏菜单</li>
              <li>添加新的页面路由</li>
              <li>实现插件页面组件</li>
              <li>插件生命周期管理</li>
            </ul>
          </div>
          
          <div>
            <Title level={4}>插件信息</Title>
            <Space orientation="vertical" size="middle">
              <div>
                <Text strong>插件名称：</Text>
                <Text>demo-plugin</Text>
              </div>
              <div>
                <Text strong>版本：</Text>
                <Text>1.0.0</Text>
              </div>
              <div>
                <Text strong>描述：</Text>
                <Text>前端插件demo</Text>
              </div>
              <div>
                <Text strong>作者：</Text>
                <Text>QBot Team</Text>
              </div>
            </Space>
          </div>
          
          <div style={{ display: 'flex', gap: '10px' }}>
            <Button type="primary">主要按钮</Button>
            <Button>普通按钮</Button>
            <Button danger>危险按钮</Button>
            <Button ghost>幽灵按钮</Button>
          </div>
          
          <Card title="嵌套卡片示例" size="small">
            <Paragraph>
              这是一个嵌套卡片示例，展示了在插件页面中可以使用各种Ant Design组件。
            </Paragraph>
          </Card>
        </Space>
      </Card>
    </div>
  );
};

export default DemoPage;
