/**
 * 右栏因子详情：头部（生命周期/编辑/删除）+ 概览/分析/快照三页签。
 * 写操作（生命周期、编辑、删除、快照增删、分析完成）统一回调 onRefreshCatalog 刷新左栏。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  App as AntApp,
  Button,
  Card,
  Flex,
  Popconfirm,
  Select,
  Space,
  Tabs,
  Tooltip,
} from 'antd';
import { DeleteOutlined, EditOutlined, ExperimentOutlined } from '@ant-design/icons';
import {
  factorApi,
  type FactorCatalogItem,
  type LifecycleStatus,
} from '@/api/factor';
import { NEXT_STATUS, factorSource, isAiProduced } from './factorMeta';
import FactorOverviewPanel from './FactorOverviewPanel';
import FactorAnalyzePanel from './FactorAnalyzePanel';
import FactorSnapshotsPanel from './FactorSnapshotsPanel';
import FactorCodePanel from './FactorCodePanel';
import FactorFormModal from './FactorFormModal';
import { QcEmpty } from '@/components/ui/DataTable';

const errMsg = (e: unknown) => (e as Error)?.message || '操作失败';

const FactorDetailPane: React.FC<{
  factor: FactorCatalogItem | null;
  onRefreshCatalog: () => void;
}> = ({ factor, onRefreshCatalog }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const navigate = useNavigate();
  const [tab, setTab] = useState<'overview' | 'analyze' | 'snapshots' | 'code'>('overview');
  const [editOpen, setEditOpen] = useState(false);
  // 编辑保存后同名覆盖不会触发 FactorCodePanel 的 useEffect，用 key 强制重挂载刷新代码 Tab
  const [codeVersion, setCodeVersion] = useState(0);
  const [categorySaving, setCategorySaving] = useState(false);

  if (!factor) {
    return (
      <Card>
        <QcEmpty title={t('factor_detail_empty')} />
      </Card>
    );
  }

  const statusLabel = (s: LifecycleStatus) => t(`factor_status_${s.toLowerCase()}`) || s;

  const changeLifecycle = async (status: LifecycleStatus) => {
    try {
      await factorApi.updateLifecycle(factor!.name, status);
      message.success(t('factor_lib_toast_status_updated') || '状态已更新');
      onRefreshCatalog();
    } catch (e) {
      message.error(errMsg(e));
      onRefreshCatalog();
    }
  };

  const changeCategory = async (category: string) => {
    setCategorySaving(true);
    try {
      await factorApi.updateCategory(factor!.name, category);
      message.success(t('factor_lib_toast_category_updated') || '分类已更新');
      onRefreshCatalog();
    } catch (e) {
      message.error(errMsg(e));
      onRefreshCatalog();
    } finally {
      setCategorySaving(false);
    }
  };

  const openEdit = () => setEditOpen(true);

  // 编辑保存成功：关弹窗、递增 codeVersion 刷新代码 Tab、刷新目录
  const handleEdited = () => {
    setEditOpen(false);
    setCodeVersion((v) => v + 1);
    onRefreshCatalog();
  };

  const remove = async () => {
    try {
      await factorApi.remove(factor!.name);
      message.success(t('factor_lib_toast_deleted') || '已删除');
      onRefreshCatalog();
    } catch (e) {
      message.error(errMsg(e));
    }
  };

  const locked = factor.builtin || factor.lifecycle_status === 'RETIRED';
  // 代码因子可在线编辑（同名覆盖）；合成因子涉及成分/权重，仍禁止在线编辑
  const isComposite = factorSource(factor) === 'composite';

  // 生命周期 → §6.2 chip 语气（与左栏表格状态列同口径：有效=ok / 观察=warn / 失效=down）
  const statusTone =
    factor.lifecycle_status === 'LIVE' ? 'ok' : factor.lifecycle_status === 'RETIRED' ? 'down' : 'warn';

  return (
    <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
      <Card size="small">
        <Flex justify="space-between" align="center" wrap="wrap" gap="small">
          <Flex gap={6} align="center" wrap>
            <span style={{ fontSize: 16, fontWeight: 650, color: 'var(--qc-text)' }}>{factor.label}</span>
            <span className="qc-cell-id">{factor.name}</span>
            <span className="qc-row-chips">
              {factor.builtin && <span className="qc-chip quiet">{t('factor_lib_builtin')}</span>}
              {factorSource(factor) === 'code' && <span className="qc-chip info">{t('factor_lib_code')}</span>}
              {factorSource(factor) === 'composite' && <span className="qc-chip pri">{t('factor_lib_composite')}</span>}
              {isAiProduced(factor) && <span className="qc-chip pri">AI</span>}
              {!factor.supported && <span className="qc-chip down">{t('factor_lib_no_data')}</span>}
            </span>
          </Flex>
          <Flex gap="small" align="center">
            {locked ? (
              <span className={`qc-chip ${statusTone}`} style={{ marginInlineEnd: 0 }}>
                {statusLabel(factor.lifecycle_status)}
              </span>
            ) : (
              <Select
                size="small"
                style={{ width: 140 }}
                value={factor.lifecycle_status}
                onChange={changeLifecycle}
                options={[
                  { value: factor.lifecycle_status, label: statusLabel(factor.lifecycle_status), disabled: true },
                  ...NEXT_STATUS[factor.lifecycle_status].map((s) => ({ value: s, label: statusLabel(s) })),
                ]}
              />
            )}
            <Tooltip title={isComposite ? t('factor_code_edit_disabled') : undefined}>
              <span>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  disabled={factor.builtin || isComposite}
                  onClick={openEdit}
                >
                  {t('factor_lib_edit') || '编辑'}
                </Button>
              </span>
            </Tooltip>
            {/* PRD §6.2「基于此因子研究」：跳 /research?seed=<name>（因子代码因子不可编辑但可作种子） */}
            <span>
              <Button
                size="small"
                icon={<ExperimentOutlined />}
                onClick={() => navigate(`/research?seed=${encodeURIComponent(factor.name)}`)}
              >
                {t('factor_research_seed')}
              </Button>
            </span>
            <Popconfirm
              title={t('factor_lib_edit_confirm') || '删除该自定义因子？'}
              disabled={factor.builtin}
              onConfirm={remove}
            >
              <Button size="small" danger icon={<DeleteOutlined />} disabled={factor.builtin}>
                {t('factor_lib_delete') || '删除'}
              </Button>
            </Popconfirm>
          </Flex>
        </Flex>
      </Card>

      <Card
        styles={{ body: { paddingTop: 8 } }}
      >
        <Tabs
          activeKey={tab}
          onChange={(k) => setTab(k as typeof tab)}
          items={[
            {
              key: 'overview',
              label: t('factor_detail_tab_overview') || '概览',
              children: (
                <FactorOverviewPanel
                  factor={factor}
                  onGoAnalyze={() => setTab('analyze')}
                  onGoCode={() => setTab('code')}
                  onCategoryChange={changeCategory}
                  categorySaving={categorySaving}
                />
              ),
            },
            {
              key: 'analyze',
              label: t('factor_detail_tab_analyze') || '分析',
              children: <FactorAnalyzePanel factor={factor} onAnalyzed={onRefreshCatalog} />,
            },
            {
              key: 'snapshots',
              label: t('factor_detail_tab_snapshots') || '快照',
              children: <FactorSnapshotsPanel factor={factor} onChanged={onRefreshCatalog} />,
              // 切进来时重挂载 → 拉最新快照（analyze 刚写完新快照，factor.name 没变，不能靠 useEffect 触发）
              destroyOnHidden: true,
            },
            {
              key: 'code',
              label: t('factor_detail_tab_code') || '代码',
              children: <FactorCodePanel key={codeVersion} factor={factor} />,
              destroyOnHidden: true,
            },
          ]}
        />
      </Card>

      <FactorFormModal
        open={editOpen}
        editing={factor}
        onCancel={() => setEditOpen(false)}
        onSaved={handleEdited}
      />
    </Space>
  );
};

export default FactorDetailPane;
