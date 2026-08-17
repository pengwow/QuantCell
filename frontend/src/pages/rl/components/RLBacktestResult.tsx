import { Card, Statistic, Row, Col, Descriptions } from 'antd';

export interface BacktestResult {
  total_pnl: number;
  final_nav: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  fills: number;
  total_fees: number;
  bar_count: number;
}

interface RLBacktestResultProps {
  result: BacktestResult;
}

export default function RLBacktestResult({ result }: RLBacktestResultProps) {
  return (
    <Card title="回测结果" style={{ marginTop: 16 }}>
      <Row gutter={16}>
        <Col span={8}>
          <Statistic
            title="总收益"
            value={result.total_pnl}
            precision={2}
            valueStyle={{ color: result.total_pnl >= 0 ? '#3f8600' : '#cf1322' }}
            prefix="¥"
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="夏普比率"
            value={result.sharpe_ratio}
            precision={4}
            valueStyle={{ color: result.sharpe_ratio >= 1 ? '#52c41a' : '#fa8c16' }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="最大回撤"
            value={result.max_drawdown}
            precision={2}
            suffix="%"
            valueStyle={{ color: '#cf1322' }}
          />
        </Col>
      </Row>

      <div style={{ marginTop: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="最终净值">
            {result.final_nav.toFixed(2)}
          </Descriptions.Item>
          <Descriptions.Item label="胜率">
            {(result.win_rate * 100).toFixed(1)}%
          </Descriptions.Item>
          <Descriptions.Item label="成交笔数">
            {result.fills}
          </Descriptions.Item>
          <Descriptions.Item label="总手续费">
            {result.total_fees.toFixed(2)}
          </Descriptions.Item>
          <Descriptions.Item label="K线数量">
            {result.bar_count}
          </Descriptions.Item>
        </Descriptions>
      </div>
    </Card>
  );
}
