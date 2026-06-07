/**
 * Worker 分享配置 Modal
 *
 * 提供分享链接的生成、复制、查看与撤销能力。
 * - 顶部：有效期 Radio + 一次性 Switch
 * - 「生成链接」按钮触发 createShareToken
 * - 生成的 URL 支持一键复制（带 fallback）
 * - 底部表格展示当前 worker 的所有 token 列表，支持撤销
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Skeleton,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CopyOutlined,
  DeleteOutlined,
  LinkOutlined,
  ReloadOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  createShareToken,
  listShareTokens,
  revokeShareToken,
} from '@/api/workerApi';
import type { ShareTokenListItem } from '@/types/worker';

// 有效期选项：value 传 null 表示不限
type ExpiresIn = 3600 | 86400 | 604800 | null;

interface WorkerShareModalProps {
  open: boolean;
  workerId: number;
  /** 选填：用于在 modal 标题中展示 */
  workerName?: string;
  onClose: () => void;
}

// 状态推导：active / revoked / expired / one_time_consumed
type TokenStatus = 'active' | 'revoked' | 'expired' | 'one_time_consumed';

const computeStatus = (item: ShareTokenListItem): TokenStatus => {
  if (item.revoked) return 'revoked';
  // 一次性已使用：view_count >= 1（且后端会消费 token，使其 revoked，但兜底判断）
  if (item.one_time && item.view_count >= 1 && !item.revoked) return 'one_time_consumed';
  if (item.expires_at) {
    const exp = new Date(item.expires_at).getTime();
    if (!Number.isNaN(exp) && exp < Date.now()) return 'expired';
  }
  return 'active';
};

const statusMeta = (status: TokenStatus) => {
  switch (status) {
    case 'active':
      return { color: 'green', key: 'status_active' };
    case 'revoked':
      return { color: 'red', key: 'status_revoked' };
    case 'expired':
      return { color: 'default', key: 'status_expired' };
    case 'one_time_consumed':
      return { color: 'orange', key: 'status_one_time_used' };
  }
};

const WorkerShareModal: React.FC<WorkerShareModalProps> = ({
  open,
  workerId,
  workerName,
  onClose,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();

  // 分享配置
  const [expiresIn, setExpiresIn] = useState<ExpiresIn>(86400);
  // 最大访问次数：null = 不限；>=1 = 限制次数（填 1 等同一次性访问）
  const [maxViews, setMaxViews] = useState<number | null>(null);

  // 当前生成的链接
  const [generatedUrl, setGeneratedUrl] = useState<string>('');
  const [generating, setGenerating] = useState<boolean>(false);

  // token 列表
  const [tokens, setTokens] = useState<ShareTokenListItem[]>([]);
  const [loadingTokens, setLoadingTokens] = useState<boolean>(false);
  const [revokingId, setRevokingId] = useState<number | null>(null);

  // 拉取 token 列表
  const fetchTokens = useCallback(async () => {
    if (!workerId) return;
    setLoadingTokens(true);
    try {
      const list = await listShareTokens(workerId);
      setTokens(Array.isArray(list) ? list : []);
    } catch (err: any) {
      // eslint-disable-next-line no-console
      console.error('获取分享 token 列表失败:', err);
      setTokens([]);
      message.error(err?.message || t('error'));
    } finally {
      setLoadingTokens(false);
    }
  }, [workerId, message, t]);

  // 打开时拉取列表
  useEffect(() => {
    if (open) {
      fetchTokens();
    }
  }, [open, fetchTokens]);

  // 关闭后重置所有状态
  useEffect(() => {
    if (!open) {
      setExpiresIn(86400);
      setMaxViews(null);
      setGeneratedUrl('');
      setGenerating(false);
      setRevokingId(null);
    }
  }, [open]);

  // 生成链接
  const handleGenerate = async () => {
    if (!workerId) return;
    setGenerating(true);
    try {
      // max_views=null 不限；填 1 等同一次性
      const isOneTime = maxViews === 1;
      const res = await createShareToken(workerId, {
        // 0 / null 表示不限；为简化只传秒数或 undefined
        expires_in_seconds: expiresIn === null ? undefined : expiresIn,
        one_time: isOneTime,
        max_views: maxViews !== null && maxViews > 1 ? maxViews : undefined,
      });
      // 拼接完整 URL：后端 url 是空 base + path，前端补全 origin
      const fullUrl = `${window.location.origin}/share/${res.token}`;
      setGeneratedUrl(fullUrl);
      message.success(t('share.link_generated'));
      // 刷新列表
      fetchTokens();
    } catch (err: any) {
      // eslint-disable-next-line no-console
      console.error('生成分享链接失败:', err);
      message.error(err?.message || t('share.generate_failed'));
    } finally {
      setGenerating(false);
    }
  };

  // 复制链接（带 fallback）
  const handleCopy = async (text: string) => {
    if (!text) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        // Fallback：选中文本
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (!ok) throw new Error('execCommand copy failed');
      }
      message.success(t('share.copied'));
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('复制失败:', err);
      message.error(t('share.copy_failed'));
    }
  };

  // 撤销
  const handleRevoke = async (shareId: number) => {
    if (!workerId) return;
    setRevokingId(shareId);
    try {
      await revokeShareToken(workerId, shareId);
      message.success(t('success'));
      fetchTokens();
    } catch (err: any) {
      // eslint-disable-next-line no-console
      console.error('撤销分享 token 失败:', err);
      message.error(err?.message || t('share.revoke_failed'));
    } finally {
      setRevokingId(null);
    }
  };

  // 表格列
  const columns: ColumnsType<ShareTokenListItem> = useMemo(
    () => [
      {
        title: t('share.token_prefix'),
        dataIndex: 'token_prefix',
        key: 'token_prefix',
        width: 180,
        render: (prefix: string) => (
          <Tooltip title={prefix}>
            <code style={{ fontSize: 12 }}>{prefix}</code>
          </Tooltip>
        ),
      },
      {
        title: t('share.access_limit'),
        key: 'access_limit',
        width: 130,
        align: 'center',
        render: (_: any, record: ShareTokenListItem) => {
          // max_views 优先：1 = 一次性（等同 one_time），>1 = 数字 N
          // 历史数据兼容：one_time=true 但 max_views=null 时仍展示"一次性"
          if (record.max_views === 1 || (record.one_time && record.max_views === null)) {
            return <Tag color="orange">{t('share.one_time')}</Tag>;
          }
          if (record.max_views !== null && record.max_views > 1) {
            return <Tag color="blue">{record.max_views}</Tag>;
          }
          return <Tag>{t('share.max_views_unlimited')}</Tag>;
        },
      },
      {
        title: t('share.view_count'),
        dataIndex: 'view_count',
        key: 'view_count',
        width: 100,
        align: 'center',
      },
      {
        title: t('share.created_at'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 170,
        render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
      {
        title: t('share.expires_at'),
        dataIndex: 'expires_at',
        key: 'expires_at',
        width: 170,
        render: (v: string | null) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : t('share.expires_in_unlimited')),
      },
      {
        title: t('share.status'),
        key: 'status',
        width: 130,
        render: (_: any, record: ShareTokenListItem) => {
          const status = computeStatus(record);
          const meta = statusMeta(status);
          return <Tag color={meta.color}>{t(`share.${meta.key}`)}</Tag>;
        },
      },
      {
        title: t('action'),
        key: 'action',
        width: 110,
        align: 'center',
        fixed: 'right',
        render: (_: any, record: ShareTokenListItem) => {
          const status = computeStatus(record);
          const disabled = status !== 'active';
          return (
            <Popconfirm
              title={t('share.confirm_revoke')}
              onConfirm={() => handleRevoke(record.id)}
              okText={t('confirm')}
              cancelText={t('cancel')}
              disabled={disabled}
            >
              <Button
                danger
                size="small"
                icon={<DeleteOutlined />}
                loading={revokingId === record.id}
                disabled={disabled}
              >
                {t('share.revoke')}
              </Button>
            </Popconfirm>
          );
        },
      },
    ],
    [t, revokingId],
  );

  const expiresInOptions: { label: string; value: ExpiresIn }[] = [
    { label: t('share.expires_in_1h'), value: 3600 },
    { label: t('share.expires_in_24h'), value: 86400 },
    { label: t('share.expires_in_7d'), value: 604800 },
    { label: t('share.expires_in_unlimited'), value: null },
  ];

  return (
    <Modal
      title={
        <Space>
          <ShareAltOutlined />
          {workerName
            ? t('share.modal_title', { name: workerName })
            : t('share.title')}
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={820}
      destroyOnClose
    >
      <Form layout="vertical">
        {/* 有效期 + 一次性 */}
        <Space size="large" wrap style={{ marginBottom: 8 }}>
          <Form.Item
            label={t('share.expires_in_label')}
            style={{ marginBottom: 12 }}
          >
            <Radio.Group
              value={expiresIn}
              onChange={(e) => setExpiresIn(e.target.value as ExpiresIn)}
              optionType="button"
              buttonStyle="solid"
              disabled={generating}
            >
              {expiresInOptions.map((opt) => (
                <Radio.Button key={String(opt.value)} value={opt.value as any}>
                  {opt.label}
                </Radio.Button>
              ))}
            </Radio.Group>
          </Form.Item>

          <Form.Item
            label={t('share.max_views_label')}
            tooltip={t('share.max_views_desc')}
            style={{ marginBottom: 12 }}
          >
            <InputNumber
              min={1}
              max={9999}
              value={maxViews ?? undefined}
              onChange={(v) => setMaxViews(v === null || v === undefined ? null : Number(v))}
              placeholder={t('share.max_views_unlimited')}
              disabled={generating}
              style={{ width: 180 }}
            />
          </Form.Item>
        </Space>

        {/* 生成链接按钮 */}
        <Form.Item>
          <Button
            type="primary"
            icon={<LinkOutlined />}
            loading={generating}
            onClick={handleGenerate}
          >
            {t('share.generate')}
          </Button>
        </Form.Item>

        {/* 生成的 URL 展示 + 复制 */}
        <Form.Item>
          <Input.Group compact>
            <Input
              style={{ width: 'calc(100% - 110px)' }}
              value={generatedUrl}
              placeholder={t('share.share_link_placeholder')}
              readOnly
            />
            <Button
              type="default"
              icon={<CopyOutlined />}
              style={{ width: 110 }}
              disabled={!generatedUrl}
              onClick={() => handleCopy(generatedUrl)}
            >
              {t('share.copy_link')}
            </Button>
          </Input.Group>
        </Form.Item>
      </Form>

      {/* 已有 token 列表 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12,
        }}
      >
        <span style={{ fontWeight: 500 }}>{t('share.token_list')}</span>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={fetchTokens}
          loading={loadingTokens}
        >
          {t('refresh')}
        </Button>
      </div>

      {loadingTokens && tokens.length === 0 ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : (
        <Table
          rowKey="id"
          columns={columns}
          dataSource={tokens}
          loading={loadingTokens}
          pagination={false}
          size="small"
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: t('share.no_tokens') }}
        />
      )}
    </Modal>
  );
};

export default WorkerShareModal;
