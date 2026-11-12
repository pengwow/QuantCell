// P2-03 标的池管理页面：可复用交易对池的 CRUD、成分维护与快照历史
// 结构对齐 StrategyManagement：useState + useEffect 加载 + Table + Modal + useTranslation
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Drawer, Flex, Input, Modal, Select, Space, Table, Tag, Timeline } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { universeApi } from '@/api';
import type { UniverseDetail, UniverseSnapshot, UniverseSummary } from '@/api';

// 时间列统一展示格式（created_at 为 ISO 8601 字符串）
const formatTime = (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss');

const UniversePage = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();

  // 列表状态
  const [universes, setUniverses] = useState<UniverseSummary[]>([]);
  const [loading, setLoading] = useState(false);

  // 新建/编辑弹窗（editingUniverse 非空即编辑态）
  const [formOpen, setFormOpen] = useState(false);
  const [editingUniverse, setEditingUniverse] = useState<UniverseSummary | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  // 成分管理抽屉
  const [detail, setDetail] = useState<UniverseDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [inputSymbols, setInputSymbols] = useState<string[]>([]);
  const [memberBusy, setMemberBusy] = useState(false);

  // 快照历史弹窗
  const [snapshotOpen, setSnapshotOpen] = useState(false);
  const [snapshots, setSnapshots] = useState<UniverseSnapshot[]>([]);
  const [snapshotLoading, setSnapshotLoading] = useState(false);

  const loadList = async () => {
    try {
      setLoading(true);
      setUniverses(await universeApi.list());
    } catch {
      message.error(t('universe_load_failed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性加载
  }, []);

  // —— 新建 / 编辑 ——

  const openCreate = () => {
    setEditingUniverse(null);
    setName('');
    setDescription('');
    setFormOpen(true);
  };

  const openEdit = (u: UniverseSummary) => {
    setEditingUniverse(u);
    setName(u.name);
    setDescription(u.description ?? '');
    setFormOpen(true);
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    try {
      setSaving(true);
      if (editingUniverse) {
        await universeApi.update(editingUniverse.id, { name: name.trim(), description: description.trim() || undefined });
        message.success(t('universe_update_success'));
      } else {
        await universeApi.create({ name: name.trim(), description: description.trim() || undefined });
        message.success(t('universe_create_success'));
      }
      setFormOpen(false);
      loadList();
    } catch {
      message.error(editingUniverse ? t('universe_update_failed') : t('universe_create_failed'));
    } finally {
      setSaving(false);
    }
  };

  // 删除走二次确认，避免误操作连带成分与快照一起丢失
  const confirmDelete = (u: UniverseSummary) => {
    modal.confirm({
      title: t('universe_delete_confirm_title'),
      content: `${u.name} · ${t('universe_delete_confirm_desc')}`,
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await universeApi.remove(u.id);
          message.success(t('universe_delete_success'));
          loadList();
        } catch {
          message.error(t('universe_delete_failed'));
        }
      },
    });
  };

  // —— 成分管理 ——

  const openDrawer = async (u: UniverseSummary) => {
    setDetail(null);
    setInputSymbols([]);
    await loadDetail(u.id);
  };

  const loadDetail = async (id: number) => {
    try {
      setDetailLoading(true);
      setDetail(await universeApi.getDetail(id));
    } catch {
      message.error(t('universe_load_failed'));
    } finally {
      setDetailLoading(false);
    }
  };

  // select tags 自由输入，支持逐个回车添加多个交易对
  const handleAddMembers = async () => {
    if (!detail || inputSymbols.length === 0) return;
    try {
      setMemberBusy(true);
      await universeApi.addMembers(detail.id, inputSymbols);
      message.success(t('universe_add_success'));
      setInputSymbols([]);
      // 成分数变化需同步回列表
      loadList();
      loadDetail(detail.id);
    } catch {
      message.error(t('universe_add_failed'));
    } finally {
      setMemberBusy(false);
    }
  };

  const handleRemoveMember = async (symbol: string) => {
    if (!detail) return;
    try {
      setMemberBusy(true);
      await universeApi.removeMembers(detail.id, [symbol]);
      message.success(t('universe_remove_success'));
      loadList();
      loadDetail(detail.id);
    } catch {
      message.error(t('universe_remove_failed'));
    } finally {
      setMemberBusy(false);
    }
  };

  // —— 快照历史 ——

  const openSnapshots = async (u: UniverseSummary) => {
    setSnapshotOpen(true);
    setSnapshots([]);
    try {
      setSnapshotLoading(true);
      setSnapshots(await universeApi.listSnapshots(u.id));
    } catch {
      message.error(t('universe_load_failed'));
    } finally {
      setSnapshotLoading(false);
    }
  };

  const columns = [
    { title: t('universe_name'), dataIndex: 'name', key: 'name' },
    {
      title: t('universe_description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (v: string | null) => v ?? '-',
    },
    { title: t('universe_member_count'), dataIndex: 'member_count', key: 'member_count', width: 100, align: 'right' as const },
    { title: t('create_time'), dataIndex: 'created_at', key: 'created_at', width: 200, render: formatTime },
    {
      title: t('action'),
      key: 'action',
      width: 280,
      render: (_: unknown, u: UniverseSummary) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openDrawer(u)}>
            {t('universe_members')}
          </Button>
          <Button type="link" size="small" onClick={() => openSnapshots(u)}>
            {t('universe_snapshots')}
          </Button>
          <Button type="link" size="small" onClick={() => openEdit(u)}>
            {t('universe_edit')}
          </Button>
          <Button type="link" size="small" danger onClick={() => confirmDelete(u)}>
            {t('universe_delete')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer>
      {/* antd 组件纵向排列统一用 Space（项目规则：禁用 Tailwind space-y-*） */}
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        <Flex justify="space-between" align="center">
          <div>
            <h2 className="text-xl font-semibold">{t('universe')}</h2>
            <p className="text-sm text-gray-500">{t('universe_desc')}</p>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('universe_create')}
          </Button>
        </Flex>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={universes}
          loading={loading}
          locale={{ emptyText: t('universe_empty') }}
          pagination={false}
        />
      </Space>

      {/* 新建 / 编辑共用弹窗 */}
      <Modal
        title={editingUniverse ? t('universe_edit') : t('universe_create')}
        open={formOpen}
        confirmLoading={saving}
        okText={t('save')}
        cancelText={t('cancel')}
        onOk={handleSave}
        onCancel={() => setFormOpen(false)}
        destroyOnHidden
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <div>
            <div className="mb-1">{t('universe_name')}</div>
            <Input
              value={name}
              placeholder={t('universe_name_placeholder')}
              onChange={(e) => setName(e.target.value)}
              onPressEnter={handleSave}
            />
          </div>
          <div>
            <div className="mb-1">{t('universe_description')}</div>
            <Input.TextArea
              value={description}
              placeholder={t('universe_desc_placeholder')}
              rows={3}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </Space>
      </Modal>

      {/* 管理成分抽屉：Tag closable 移除 + Select tags 自由输入添加 */}
      <Drawer
        title={detail ? `${t('universe_members')} - ${detail.name}` : t('universe_members')}
        width={480}
        open={!!detail || detailLoading}
        onClose={() => setDetail(null)}
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <Flex gap="small">
            <Select
              mode="tags"
              className="flex-1"
              value={inputSymbols}
              placeholder={t('universe_add_symbols_placeholder')}
              options={[]}
              onChange={setInputSymbols}
            />
            <Button type="primary" loading={memberBusy} disabled={inputSymbols.length === 0} onClick={handleAddMembers}>
              {t('universe_add_symbol')}
            </Button>
          </Flex>
          <Flex gap="small" wrap="wrap">
            {detail?.members.map((sym) => (
              <Tag key={sym} closable={!memberBusy} onClose={() => handleRemoveMember(sym)}>
                {sym}
              </Tag>
            ))}
            {detail && detail.members.length === 0 && <span className="text-sm text-gray-500">{t('universe_empty')}</span>}
          </Flex>
        </Space>
      </Drawer>

      {/* 快照历史：Timeline 展示每次快照时间 + 成分标签 */}
      <Modal
        title={t('universe_snapshots')}
        open={snapshotOpen}
        footer={null}
        width={520}
        onCancel={() => setSnapshotOpen(false)}
      >
        {snapshotLoading ? (
          <div className="py-6 text-center text-sm text-gray-500">{t('loading')}</div>
        ) : snapshots.length === 0 ? (
          <div className="py-6 text-center text-sm text-gray-500">{t('universe_empty')}</div>
        ) : (
          <Timeline
            items={snapshots.map((s) => ({
              children: (
                <div>
                  <div className="text-xs text-gray-500">{formatTime(s.created_at)}</div>
                  <Flex gap="small" wrap="wrap" className="mt-1">
                    {s.symbols.map((sym) => (
                      <Tag key={sym}>{sym}</Tag>
                    ))}
                  </Flex>
                </div>
              ),
            }))}
          />
        )}
      </Modal>
    </PageContainer>
  );
};

export default UniversePage;
