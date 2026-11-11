import { useEffect, useState } from 'react';
import type { Key } from 'react';
import { App as AntdApp, Button, Card, Input, Modal, Select, Space, Table, Tag, Tooltip } from 'antd';
import type { TableProps } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { ensembleApi } from '@/api/ensembleApi';
import type { EnsembleInfo } from '@/api/ensembleApi';
import { modelApi } from '@/api/modelApi';
import type { UnifiedModelRow } from '@/api/modelApi';

// 与后端 _STRATEGY_MAP 对齐的投票策略
const STRATEGY_OPTIONS = [
  { value: 'soft_vote', label: 'Soft Vote（软投票）' },
  { value: 'hard_vote', label: 'Hard Vote（硬投票）' },
  { value: 'weighted', label: 'Weighted（加权）' },
];

// 模型文件名 → stem:后端契约用 stem,解析为 MODELS_DIR/{stem}.zip
const fileNameToStem = (name: string) => name.replace(/\.zip$/, '');

export default function EnsembleWorkbench() {
  const { message, modal } = AntdApp.useApp();
  const [ensembles, setEnsembles] = useState<EnsembleInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  // 创建区:投票策略 + 已选模型 stem(Tag 可移除)
  const [strategy, setStrategy] = useState('soft_vote');
  const [selected, setSelected] = useState<string[]>([]);

  // 模型选择弹窗:复用模型总表数据,默认过滤文件缺失条目
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [candidates, setCandidates] = useState<UnifiedModelRow[]>([]);
  const [searchText, setSearchText] = useState('');
  const [modalSelected, setModalSelected] = useState<Key[]>([]);

  const loadEnsembles = async () => {
    setLoading(true);
    try {
      const data = await ensembleApi.listEnsembles();
      setEnsembles(Array.isArray(data) ? data : []);
    } catch {
      message.error('加载集成列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEnsembles();
  }, []);

  const openModal = async () => {
    setModalOpen(true);
    setModalLoading(true);
    setSearchText('');
    try {
      const rows = await modelApi.unifiedModels();
      // 文件缺失(size_mb == null)的条目无法参与集成,直接过滤
      setCandidates(Array.isArray(rows) ? rows.filter((r) => r.size_mb != null) : []);
      // 重开弹窗时回显已选
      setModalSelected([...selected]);
    } catch {
      message.error('加载模型列表失败');
    } finally {
      setModalLoading(false);
    }
  };

  const filteredCandidates = candidates.filter((r) => {
    if (!searchText) return true;
    const name = (r.model_id ?? r.file_name).toLowerCase();
    return name.includes(searchText.toLowerCase());
  });

  const confirmSelect = () => {
    setSelected(modalSelected.map(String));
    setModalOpen(false);
  };

  const handleCreate = async () => {
    if (selected.length === 0) return;
    setCreating(true);
    try {
      const result = await ensembleApi.createEnsemble({ strategy, model_paths: selected });
      message.success(`集成 ${result.ensemble_id} 创建成功`);
      if (result.skipped?.length) {
        message.warning(`其中 ${result.skipped.length} 个模型加载失败被跳过`);
      }
      setSelected([]);
      setModalSelected([]);
      await loadEnsembles();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '创建失败');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = (record: EnsembleInfo) => {
    modal.confirm({
      title: '删除集成',
      content: `确定删除集成 ${record.id} 吗？该操作不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await ensembleApi.deleteEnsemble(record.id);
        message.success('集成已删除');
        loadEnsembles();
      },
    });
  };

  const candidateColumns: TableProps<UnifiedModelRow>['columns'] = [
    {
      title: '模型名称', dataIndex: 'file_name', key: 'file_name', ellipsis: true,
      render: (text: string, record) => (
        <Tooltip title={record.model_id ? `${record.model_id}（${text}）` : text}>
          <span className="truncate">{record.model_id ?? text}</span>
        </Tooltip>
      ),
    },
    {
      title: '算法', dataIndex: 'algorithm', key: 'algorithm', width: 110,
      render: (a: string) => (a && a !== '-' ? <Tag color="blue">{a}</Tag> : '-'),
    },
    {
      title: '大小', dataIndex: 'size_mb', key: 'size_mb', width: 90, align: 'right',
      render: (v: number | null) => (v == null ? '-' : `${v} MB`),
    },
  ];

  const ensembleColumns: TableProps<EnsembleInfo>['columns'] = [
    {
      title: '集成 ID', dataIndex: 'id', key: 'id', width: 120,
      render: (id: string) => <Tag>{id}</Tag>,
    },
    {
      title: '策略', dataIndex: 'strategy', key: 'strategy', width: 130,
      render: (s: string) => <Tag color="blue">{s}</Tag>,
    },
    { title: '模型数', dataIndex: 'models', key: 'models', width: 90, align: 'right' },
    {
      title: '模型列表', key: 'model_paths', width: 280,
      render: (_, record) => {
        const members = record.members ?? [];
        // 旧记录无 members 字段时降级为纯名称列表(维持原展示)
        if (members.length === 0) {
          return (
            <Tooltip title={record.model_paths.join('、')}>
              <span className="truncate">{record.model_paths.join('、') || '-'}</span>
            </Tooltip>
          );
        }
        return (
          <Tooltip title={members.map((m) => `${m.stem}（${m.action_space === 'box' ? '连续' : '离散'}）`).join('、')}>
            <Space size={4} wrap>
              {members.map((m) => (
                <span key={m.stem}>
                  {/* 成员动作空间:box=连续(0~1) / discrete=离散投票映射(spec §5) */}
                  <Tag color={m.action_space === 'box' ? 'blue' : 'default'}>
                    {m.action_space === 'box' ? '连续' : '离散'}
                  </Tag>
                  {m.stem}
                </span>
              ))}
            </Space>
          </Tooltip>
        );
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      className: 'whitespace-nowrap',
      render: (ts: number | null) => (ts ? dayjs(ts * 1000).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '操作', key: 'actions', width: 90, fixed: 'right',
      render: (_, record) => (
        <Tooltip title="删除">
          <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} />
        </Tooltip>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card title="创建集成" size="small">
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <Space wrap>
            <Select value={strategy} onChange={setStrategy} style={{ width: 200 }} options={STRATEGY_OPTIONS} />
            <Button icon={<PlusOutlined />} onClick={openModal}>选择模型</Button>
            <Button type="primary" disabled={selected.length === 0} loading={creating} onClick={handleCreate}>
              创建集成{selected.length > 0 ? `（${selected.length}）` : ''}
            </Button>
          </Space>
          {selected.length > 0 && (
            <Space size={4} wrap>
              {selected.map((s) => (
                <Tag
                  key={s}
                  closable
                  onClose={() => setSelected((prev) => prev.filter((x) => x !== s))}
                >
                  {s}
                </Tag>
              ))}
            </Space>
          )}
        </Space>
      </Card>

      <Card title="集成列表" size="small">
        <Table<EnsembleInfo>
          columns={ensembleColumns}
          dataSource={ensembles}
          loading={loading}
          rowKey="id"
          size="small"
          scroll={{ x: 880 }}
          pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条` }}
        />
      </Card>

      <Modal
        title="选择模型"
        open={modalOpen}
        width={680}
        onOk={confirmSelect}
        onCancel={() => setModalOpen(false)}
        okText="确定"
        cancelText="取消"
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <Input
            placeholder="搜索模型名称"
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <Table<UnifiedModelRow>
            columns={candidateColumns}
            dataSource={filteredCandidates}
            loading={modalLoading}
            size="small"
            pagination={{ pageSize: 8, showTotal: (total) => `共 ${total} 条` }}
            // rowKey 用 stem:确认后直接作为 model_paths 传给后端,免去二次映射
            rowKey={(r) => fileNameToStem(r.file_name)}
            rowSelection={{
              type: 'checkbox',
              selectedRowKeys: modalSelected,
              onChange: (keys) => setModalSelected(keys),
            }}
          />
        </Space>
      </Modal>
    </Space>
  );
}
