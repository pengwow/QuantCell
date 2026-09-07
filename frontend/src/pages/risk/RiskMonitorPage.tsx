import { useState, useEffect } from 'react';
import { Card, Button, Statistic, Row, Col, Form, Input, message } from 'antd';
import { ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined, SafetyOutlined } from '@ant-design/icons';
import PageContainer from '@/components/PageContainer';
import { riskApi, RiskMetrics, RiskCheckResult } from '@/api/riskApi';

export default function RiskMonitorPage() {
  const [metrics, setMetrics] = useState<RiskMetrics | null>(null);
  const [checkResult, setCheckResult] = useState<RiskCheckResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => { loadMetrics(); }, []);

  const loadMetrics = async () => {
    setLoading(true);
    try {
      const data = await riskApi.getMetrics();
      setMetrics(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const handleCheck = async (values: { order: string; portfolio: string }) => {
    try {
      const order = JSON.parse(values.order);
      const portfolio = JSON.parse(values.portfolio);
      const result = await riskApi.checkOrder({ order, portfolio });
      setCheckResult(result);
    } catch {
      message.error('JSON格式错误或检查失败');
    }
  };

  const handleReset = async () => {
    try {
      await riskApi.resetDaily();
      message.success('每日计数已重置');
      loadMetrics();
    } catch { message.error('重置失败'); }
  };

  return (
    <PageContainer title="风控监控">
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="总检查次数" value={metrics?.total_checks ?? '-'} /></Card></Col>
        <Col span={6}><Card><Statistic title="拒绝订单数" value={metrics?.rejected_orders ?? '-'} valueStyle={{ color: '#cf1322' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="拒绝率" value={metrics?.rejection_rate ?? '-'} suffix="%" /></Card></Col>
        <Col span={6}>
          <Card>
            <Button icon={<ReloadOutlined />} onClick={handleReset} loading={loading}>重置每日计数</Button>
          </Card>
        </Col>
      </Row>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card title="订单风控检查">
          <Form form={form} onFinish={handleCheck} layout="vertical">
            <Form.Item name="order" label="订单 JSON" rules={[{ required: true }]}>
              <Input.TextArea rows={3} placeholder='{"symbol":"BTC-USDT","side":"Buy","quantity":0.1,"price":50000}' />
            </Form.Item>
            <Form.Item name="portfolio" label="组合 JSON" rules={[{ required: true }]}>
              <Input.TextArea rows={2} placeholder='{"cash":{"USD":200000}}' />
            </Form.Item>
            <Button type="primary" htmlType="submit" icon={<SafetyOutlined />}>检查</Button>
          </Form>
        </Card>

        <Card title="检查结果">
          {checkResult ? (
            <div style={{ textAlign: 'center', padding: 24 }}>
              {checkResult.passed ? (
                <><CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a' }} /><p>通过</p></>
              ) : (
                <><CloseCircleOutlined style={{ fontSize: 48, color: '#cf1322' }} /><p>拒绝: {checkResult.reason}</p></>
              )}
            </div>
          ) : (
            <p style={{ color: '#999', textAlign: 'center', padding: 24 }}>提交订单查看结果</p>
          )}
        </Card>
      </div>
    </PageContainer>
  );
}
