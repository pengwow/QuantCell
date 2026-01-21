/**
 * 数据池表单组件
 * 功能：用于创建和编辑数据池的表单
 * @param props 组件属性
 */
import { useEffect } from 'react';
import { Form, Input, Button, Space, Transfer, Spin } from 'antd';

interface AssetPoolFormProps {
  initialData?: {
    id?: string;
    name: string;
    description: string;
  };
  onSubmit: (data: {
    id?: string;
    name: string;
    description: string;
    assets: string[];
  }) => void;
  onCancel: () => void;
  assetPoolNames: string[];
  // 资产相关属性
  availableAssets: string[];
  selectedAssets: string[];
  onAssetsChange: (assets: string[]) => void;
  symbolsLoading: boolean;
  onSearchSymbols: (direction: string, value: string) => void;
  hasMore: boolean;
  onLoadMore: () => void;
}

const AssetPoolForm = (props: AssetPoolFormProps) => {
  const { 
    initialData = { name: '', description: '' }, 
    onSubmit, 
    onCancel,
    assetPoolNames,
    // 资产相关属性
    availableAssets,
    selectedAssets,
    onAssetsChange,
    symbolsLoading,
    onSearchSymbols,
    hasMore,
    onLoadMore
  } = props;
  
  const [form] = Form.useForm();

  // 监听initialData变化，动态更新表单值
  useEffect(() => {
    if (initialData) {
      form.setFieldsValue({
        name: initialData.name,
        description: initialData.description
      });
    }
  }, [initialData, form]);

  const handleSubmit = (values: { name: string; description: string }) => {
    onSubmit({
      id: initialData.id,
      ...values,
      assets: selectedAssets
    });
  };

  return (
    <div className="asset-pool-form-container">
      {/* <h3>{initialData.id ? '编辑资产池' : '创建资产池'}</h3> */}
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          name: initialData.name,
          description: initialData.description
        }}
        onFinish={handleSubmit}
        className="asset-pool-form"
      >
        <Form.Item
          name="name"
          label="资产池名称"
          rules={[
            { required: true, message: '请输入资产池名称' },
            { min: 2, message: '资产池名称长度不能少于2个字符' },
            {
              validator: (_, value) => {
                // 检查名称是否已存在
                const isDuplicate = assetPoolNames.some(
                  name => name === value && name !== initialData?.name
                );
                return isDuplicate ? Promise.reject(new Error('资产池名称已存在')) : Promise.resolve();
              }
            }
          ]}
        >
          <Input placeholder="请输入资产池名称" />
        </Form.Item>

        <Form.Item
        name="description"
        label="数据池描述"
        rules={[
            { required: true, message: '请输入数据池描述' }
          ]}
        >
          <Input.TextArea rows={4} placeholder="请输入资产池描述" />
        </Form.Item>

        <Form.Item
          label="资产选择"
          rules={[
            {
              validator: () => {
                // 检查是否至少选择了一个资产
                return selectedAssets.length > 0 ? Promise.resolve() : Promise.reject(new Error('请至少选择一个资产'));
              }
            }
          ]}
        >
          <Spin spinning={symbolsLoading} tip="加载资产列表中...">
            <Transfer
              dataSource={availableAssets.map(symbol => ({ key: symbol, title: symbol }))}
              showSearch
              onSearch={onSearchSymbols}
              filterOption={(inputValue, item) =>
                item.title.toLowerCase().includes(inputValue.toLowerCase())
              }
              targetKeys={selectedAssets}
              onChange={(targetKeys) => {
                // 将Key[]转换为string[]类型
                const stringKeys = targetKeys.map(key => String(key));
                onAssetsChange(stringKeys);
              }}
              render={item => item.title}
              titles={['可用资产', '已选择资产']}
              styles={{ section: { width: 300, height: 400 } }}
              actions={['添加', '移除']}
              footer={({ direction }) => {
                if (direction === 'left' && hasMore && !symbolsLoading) {
                  return (
                    <Button
                      type="link"
                      onClick={onLoadMore}
                      disabled={symbolsLoading}
                    >
                      {symbolsLoading ? '加载中...' : '加载更多'}
                    </Button>
                  );
                }
                return null;
              }}
            />
          </Spin>
        </Form.Item>

        <Form.Item className="form-actions">
          <Space>
            <Button type="default" onClick={onCancel}>
              取消
            </Button>
            <Button type="primary" htmlType="submit">
              {initialData.id ? '更新' : '创建'}
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </div>
  );
};

export default AssetPoolForm;
