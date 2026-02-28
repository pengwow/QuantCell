import { useTranslation } from 'react-i18next';
import { Card, Button, Table } from 'antd';
import { IconPlus } from '@tabler/icons-react';
import PageContainer from '@/components/PageContainer';

const DataPoolPage = () => {
  const { t } = useTranslation();

  const columns = [
    {
      title: '数据池名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: '时间周期',
      dataIndex: 'timeframe',
      key: 'timeframe',
    },
    {
      title: '数据范围',
      dataIndex: 'range',
      key: 'range',
    },
    {
      title: '操作',
      key: 'action',
      render: () => (
        <Button type="link">管理</Button>
      ),
    },
  ];

  return (
    <PageContainer title={t('data_pool_management')}>
      <div className="space-y-4">
        <div className="flex justify-end items-center">
          <Button type="primary" icon={<IconPlus size={16} />}>
            新建数据池
          </Button>
        </div>
        <Card>
          <Table columns={columns} dataSource={[]} />
        </Card>
      </div>
    </PageContainer>
  );
};

export default DataPoolPage;
