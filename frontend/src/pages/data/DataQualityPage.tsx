import { useTranslation } from 'react-i18next';
import { Card, Table, Tag, Progress } from 'antd';
import PageContainer from '@/components/PageContainer';

const DataQualityPage = () => {
  const { t } = useTranslation();

  const columns = [
    {
      title: '数据池',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '完整性',
      dataIndex: 'completeness',
      key: 'completeness',
      render: (value: number) => (
        <Progress percent={value} size="small" />
      ),
    },
    {
      title: '一致性',
      dataIndex: 'consistency',
      key: 'consistency',
      render: (value: number) => (
        <Progress percent={value} size="small" />
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'good' ? 'success' : status === 'warning' ? 'warning' : 'error'}>
          {status === 'good' ? '良好' : status === 'warning' ? '警告' : '错误'}
        </Tag>
      ),
    },
    {
      title: '最后检查',
      dataIndex: 'lastCheck',
      key: 'lastCheck',
    },
  ];

  return (
    <PageContainer title={t('data_quality')}>
      <Card>
        <Table columns={columns} dataSource={[]} />
      </Card>
    </PageContainer>
  );
};

export default DataQualityPage;
