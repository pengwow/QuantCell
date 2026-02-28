import { useTranslation } from 'react-i18next';
import { Card, Button, Form, Select, DatePicker } from 'antd';
import { IconDownload } from '@tabler/icons-react';
import PageContainer from '@/components/PageContainer';

const { RangePicker } = DatePicker;

const DataCollectionPage = () => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  const handleSubmit = (values: unknown) => {
    console.log('Form values:', values);
  };

  return (
    <PageContainer title={t('data_collection')}>
      <div className="space-y-4">
        <Card title="数据采集配置">
          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
          >
            <Form.Item
              label="交易所"
              name="exchange"
              rules={[{ required: true, message: '请选择交易所' }]}
            >
              <Select placeholder="选择交易所">
                <Select.Option value="binance">Binance</Select.Option>
                <Select.Option value="okx">OKX</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="交易对"
              name="symbol"
              rules={[{ required: true, message: '请输入交易对' }]}
            >
              <Select placeholder="选择交易对" mode="multiple">
                <Select.Option value="BTCUSDT">BTCUSDT</Select.Option>
                <Select.Option value="ETHUSDT">ETHUSDT</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="时间周期"
              name="timeframe"
              rules={[{ required: true, message: '请选择时间周期' }]}
            >
              <Select placeholder="选择时间周期">
                <Select.Option value="1m">1分钟</Select.Option>
                <Select.Option value="5m">5分钟</Select.Option>
                <Select.Option value="1h">1小时</Select.Option>
                <Select.Option value="1d">1天</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="时间范围"
              name="dateRange"
              rules={[{ required: true, message: '请选择时间范围' }]}
            >
              <RangePicker style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" icon={<IconDownload size={16} />}>
                开始采集
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    </PageContainer>
  );
};

export default DataCollectionPage;
