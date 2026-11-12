// P2-06 Agent Token 管理页面：签发（明文仅展示一次）、用量查看与软撤销
// 结构：useState + useEffect 加载 + Table + Modal + useTranslation
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, App, Button, Flex, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { agentTokensApi } from '@/api';
import type { AgentTokenInfo } from '@/api';

// 时间列统一展示格式（ISO 8601 字符串；null 表示未使用/永不过期）
const formatTime = (value: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : ' ');

const AgentTokenPage = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();

  const [tokens, setTokens] = useState<AgentTokenInfo[]>([]);
  const [loading, setLoading] = useState(false);

  // 签发表单
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState('');
  const [scope, setScope] = useState<string>('read');
  const [expiresDays, setExpiresDays] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  // 签发成功后的一次性明文展示：Modal 关闭即永不可见（后端只存摘要）
  const [issuedToken, setIssuedToken] = useState<string | null>(null);

  const loadList = async () => {
    try {
      setLoading(true);
      setTokens(await agentTokensApi.list());
    } catch {
      message.error(t('agentToken_load_failed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性加载
  }, []);

  const handleIssue = async () => {
    if (!name.trim()) return;
    try {
      setSaving(true);
      const res = await agentTokensApi.issue({
        name: name.trim(),
        scope,
        expires_days: expiresDays ?? undefined,
      });
      setFormOpen(false);
      setIssuedToken(res.token);
      loadList();
    } catch {
      message.error(t('agentToken_issue_failed'));
    } finally {
      setSaving(false);
    }
  };

  // 撤销为软删除：立即失效但保留审计记录
  const confirmRevoke = (tk: AgentTokenInfo) => {
    modal.confirm({
      title: t('agentToken_revoke_confirm_title'),
      content: `${tk.name} · ${t('agentToken_revoke_confirm_desc')}`,
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await agentTokensApi.revoke(tk.id);
          message.success(t('agentToken_revoke_success'));
          loadList();
        } catch {
          message.error(t('agentToken_revoke_failed'));
        }
      },
    });
  };

  const columns = [
    { title: t('agentToken_name'), dataIndex: 'name' },
    {
      title: t('agentToken_scope'),
      dataIndex: 'scope',
      width: 110,
      render: (v: string) => <Tag color={v === 'write' ? 'orange' : 'blue'}>{v}</Tag>,
    },
    {
      title: t('agentToken_expires_at'),
      dataIndex: 'expires_at',
      width: 180,
      render: (v: string | null) => (v ? formatTime(v) : t('agentToken_never_expires')),
    },
    {
      title: t('agentToken_last_used'),
      dataIndex: 'last_used_at',
      width: 180,
      render: formatTime,
    },
    { title: t('agentToken_use_count'), dataIndex: 'use_count', width: 100 },
    {
      title: t('agentToken_status'),
      dataIndex: 'revoked',
      width: 100,
      render: (revoked: boolean) =>
        revoked ? <Tag color="red">{t('agentToken_revoked')}</Tag> : <Tag color="green">{t('agentToken_active')}</Tag>,
    },
    {
      title: t('agentToken_actions'),
      width: 90,
      render: (_: unknown, tk: AgentTokenInfo) =>
        tk.revoked ? null : (
          <Button size="small" danger onClick={() => confirmRevoke(tk)}>
            {t('agentToken_revoke')}
          </Button>
        ),
    },
  ];

  return (
    <PageContainer title={t('agentToken_settings')}>
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        <Alert type="info" showIcon title={t('agentToken_intro')} />
        <Flex justify="end">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setName('');
              setScope('read');
              setExpiresDays(null);
              setFormOpen(true);
            }}
          >
            {t('agentToken_issue')}
          </Button>
        </Flex>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={tokens}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
        />
      </Space>

      {/* 签发表单 */}
      <Modal
        title={t('agentToken_issue')}
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={handleIssue}
        okText={t('agentToken_issue')}
        okButtonProps={{ disabled: !name.trim() }}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex', marginTop: 8 }}>
          <Input
            placeholder={t('agentToken_name_placeholder')}
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
          />
          <Select value={scope} style={{ width: '100%' }} onChange={setScope}
            options={[
              { value: 'read', label: t('agentToken_scope_read') },
              { value: 'write', label: t('agentToken_scope_write') },
            ]}
          />
          <InputNumber
            min={1}
            max={3650}
            style={{ width: '100%' }}
            placeholder={t('agentToken_expires_hint')}
            value={expiresDays}
            onChange={(v) => setExpiresDays(v ?? null)}
            suffix={t('agentToken_days')}
          />
        </Space>
      </Modal>

      {/* 一次性明文展示：仅此一次 */}
      <Modal
        title={t('agentToken_issue_success')}
        open={issuedToken !== null}
        onCancel={() => setIssuedToken(null)}
        footer={[
          <Button key="ok" type="primary" onClick={() => setIssuedToken(null)}>
            {t('agentToken_saved_done')}
          </Button>,
        ]}
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <Alert type="warning" showIcon title={t('agentToken_issue_warning')} />
          <Typography.Text code copyable={{ text: issuedToken ?? '' }} style={{ maxWidth: '100%' }} ellipsis>
            {issuedToken}
          </Typography.Text>
        </Space>
      </Modal>
    </PageContainer>
  );
};

export default AgentTokenPage;
