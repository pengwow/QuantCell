import { useTranslation } from 'react-i18next';
import { useEffect } from 'react';
import { Card, Button, Table } from 'antd';
import { IconPlus } from '@tabler/icons-react';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/router';

const DataPoolPage = () => {
  const { t } = useTranslation();

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('data_pool_management') || '数据池管理');
  }, [t]);

  const columns = [
    {
      title: t('data_pool_name') || '数据池名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('symbol') || '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: t('timeframe') || '时间周期',
      dataIndex: 'timeframe',
      key: 'timeframe',
    },
    {
      title: t('data_range') || '数据范围',
      dataIndex: 'range',
      key: 'range',
    },
    {
      title: t('action') || '操作',
      key: 'action',
      render: () => (
        <Button type="link">{t('manage') || '管理'}</Button>
      ),
    },
  ];

  return (
    <PageContainer title={t('data_pool_management') || '数据池管理'}>
      <div className="space-y-4">
        <div className="flex justify-end items-center">
          <Button type="primary" icon={<IconPlus size={16} />}>
            {t('new_data_pool') || '新建数据池'}
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
