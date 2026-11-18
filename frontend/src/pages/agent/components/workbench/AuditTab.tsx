/**
 * 右栏 ⑥ 审计：GET /agent/audit（agent_tool_audit，created_at 倒序）。
 *
 * 筛选：工具名前缀 + result_status（实际值域 success/error/blocked_approval/
 * blocked_scope/invalid_params，见后端 agent/tools/registry.py 落库口径）。
 * 分页：limit 50 + offset 累积「加载更多」（与工作台其余表格一致：不分页器，固定窗口）。
 * 行展开显示 args_redacted（落库时已脱敏的 JSON 文本，前端只做格式化）。
 * 仅激活 Tab 时拉取；首次进入才请求，筛选变化即回到第一页。
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Empty, Input, Select, Spin, Table, Tag, Tooltip } from 'antd';
import type { TableColumnsType } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { queryToolAudit } from '@/api/agentApi';
import type { ToolAuditRow } from '@/api/agentApi';
import { formatTimestamp } from '@/utils/format';
import { useWorkbenchStore } from '../../store/workbenchStore';
import { AUDIT_STATUSES, AUDIT_STATUS_COLORS, formatAuditArgs } from './workbenchFormat';

const PAGE_SIZE = 50;

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err));

export default function AuditTab() {
  const { t } = useTranslation();
  const isActive = useWorkbenchStore((s) => s.activeTab) === 'audit';

  const [toolInput, setToolInput] = useState('');
  /** 已提交的工具名筛选（Input.Search 回车/点搜索才生效，避免每个字符打一次后端） */
  const [toolQuery, setToolQuery] = useState('');
  const [statusQuery, setStatusQuery] = useState<string | undefined>(undefined);

  const [rows, setRows] = useState<ToolAuditRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (offset: number) => {
      setLoading(true);
      try {
        const res = await queryToolAudit({
          tool: toolQuery || undefined,
          result_status: statusQuery,
          limit: PAGE_SIZE,
          offset,
        });
        const page = res?.audits ?? [];
        setTotal(res?.total ?? 0);
        setRows((prev) => (offset === 0 ? page : [...prev, ...page]));
        setError(null);
      } catch (err) {
        // 后端未起 / 参数非法：保留已加载行，只提示（首屏失败则展示空态）
        setError(errText(err));
        if (offset === 0) {
          setRows([]);
          setTotal(0);
        }
      } finally {
        setLoading(false);
        setLoaded(true);
      }
    },
    [toolQuery, statusQuery],
  );

  useEffect(() => {
    if (!isActive) return;
    load(0);
  }, [isActive, load]);

  const columns: TableColumnsType<ToolAuditRow> = [
    {
      title: t('wb_audit_time'),
      dataIndex: 'created_at',
      width: 150,
      // ponytail: 库列是 UTC naive，FastAPI 序列化后无时区后缀，formatTimestamp 按本地时间解释
      // （与全站表格口径一致）；真要做时区正确显示需后端带 Z 或走 dayjs UTC 插件
      render: (v: string) => <span className="wb-nowrap-mono">{formatTimestamp(v)}</span>,
    },
    {
      title: t('wb_audit_tool'),
      dataIndex: 'tool',
      width: 150,
      ellipsis: true,
      render: (v: string, row) =>
        row.args_hash ? <Tooltip title={`hash: ${row.args_hash}`}><span className="wb-nowrap-mono">{v}</span></Tooltip> : v,
    },
    {
      title: t('wb_audit_status'),
      dataIndex: 'result_status',
      width: 110,
      render: (v: string) => <Tag color={AUDIT_STATUS_COLORS[v] ?? 'default'}>{v}</Tag>,
    },
    {
      title: t('wb_audit_user'),
      dataIndex: 'user',
      width: 110,
      ellipsis: true,
      render: (v?: string | null) => v || '-',
    },
    {
      title: t('wb_audit_token'),
      dataIndex: 'token',
      width: 80,
      ellipsis: true,
      render: (v?: string | null) => <span className="wb-nowrap-mono">{v || '-'}</span>,
    },
    {
      title: t('wb_audit_duration'),
      dataIndex: 'duration_ms',
      width: 76,
      align: 'right',
      render: (v?: number | null) => (v == null ? '-' : `${v}ms`),
    },
  ];

  return (
    <div className="wb-audit">
      <div className="wb-audit-toolbar">
        <Input.Search
          size="small"
          allowClear
          placeholder={t('wb_audit_filter_tool_ph')}
          value={toolInput}
          onChange={(e) => setToolInput(e.target.value)}
          onSearch={(v) => setToolQuery(v.trim())}
          className="wb-audit-filter"
        />
        <Select
          size="small"
          allowClear
          placeholder={t('wb_audit_filter_status')}
          value={statusQuery}
          onChange={(v) => setStatusQuery(v)}
          className="wb-audit-status"
          options={AUDIT_STATUSES.map((s) => ({ value: s, label: t(`wb_audit_status_${s}`) }))}
        />
        <Tooltip title={t('refresh')}>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => load(0)} loading={loading} />
        </Tooltip>
      </div>

      {error && <Alert type="warning" showIcon title={t('wb_audit_load_failed', { err: error })} />}

      {!loaded ? (
        <div className="wb-center-spin">
          <Spin size="small" />
        </div>
      ) : rows.length === 0 ? (
        <div className="wb-placeholder">
          <Empty description={t('wb_audit_no_rows')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      ) : (
        <>
          <div className="wb-list-meta">{t('total_items', { total })}</div>
          <Table<ToolAuditRow>
            size="small"
            rowKey={(r) => String(r.id)}
            dataSource={rows}
            columns={columns}
            pagination={false}
            expandable={{
              expandedRowRender: (record) => (
                <pre className="wb-audit-args">{formatAuditArgs(record.args_redacted)}</pre>
              ),
              rowExpandable: (record) => record.args_redacted != null && record.args_redacted !== '',
            }}
            locale={{ emptyText: t('wb_audit_no_rows') }}
          />
          {rows.length < total && (
            <div className="wb-list-footer">
              <Button size="small" loading={loading} onClick={() => load(rows.length)}>
                {t('wb_audit_load_more')}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
