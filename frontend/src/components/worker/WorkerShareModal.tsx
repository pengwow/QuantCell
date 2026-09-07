/**
 * Worker 分享配置 Modal
 *
 * 提供分享链接的生成、复制、查看与撤销能力。
 * - 顶部：有效期 Radio + 最大访问次数 InputNumber
 * - 「生成链接」按钮触发 createShareToken（自动走远端 quantcell.top 分发）
 * - 生成的 URL 支持一键复制（带 fallback）
 * - 底部表格展示当前 worker 的所有 token 列表，支持撤销与重试
 *
 * 说明：
 * - 本地分享模式已下线，分享功能完全走远端 quantcell.top 分发
 * - 远端凭据通过 ensure_remote_credentials 自动按需注册，前端无需配置 UI
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App,
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  QRCode,
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
  DownloadOutlined,
  LinkOutlined,
  ReloadOutlined,
  ShareAltOutlined,
  StopOutlined,
  WechatOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  createShareToken,
  listShareTokens,
  revokeShareToken,
  deleteShareToken,
  retryShareRemoteUpload,
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
  // 最近一次分享的 worker 名称（用于微信文案）
  const [sharedWorkerName, setSharedWorkerName] = useState<string>('');

  // 二维码 DOM 引用（用于下载 PNG）
  const qrCanvasRef = useRef<HTMLDivElement>(null);

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
      // 远端上传成功才有 short_url;失败时仍返回 token,但不展示链接
      if (res.short_url) {
        setGeneratedUrl(res.short_url);
        message.success(t('share.link_generated'));
      } else if (res.remote_warning) {
        // 远端上传失败:给出非阻塞提示
        message.warning(res.remote_warning);
      } else {
        message.warning(t('share.generate_failed'));
      }
      setSharedWorkerName(workerName || '');
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

  // 通用文本复制（带 fallback）
  const copyToClipboard = async (text: string): Promise<boolean> => {
    if (!text) return false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  };

  // 下载二维码 PNG
  const handleDownloadQR = () => {
    if (!qrCanvasRef.current) return;
    // qrcode.react 渲染成 canvas / svg，取第一个 canvas
    const canvas = qrCanvasRef.current.querySelector<HTMLCanvasElement>('canvas');
    if (!canvas) {
      message.error(t('share.qr_download_failed') || '二维码下载失败');
      return;
    }
    try {
      const dataUrl = canvas.toDataURL('image/png');
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = `quantcell-share-${sharedWorkerName || workerId}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      message.success(t('share.qr_downloaded') || '二维码已下载');
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('下载二维码失败:', err);
      message.error(t('share.qr_download_failed') || '二维码下载失败');
    }
  };

  // 复制为微信分享文案（标题 + 摘要 + 链接）
  const handleCopyWechatText = async () => {
    if (!generatedUrl) return;
    const title = t('share.wechat_text_title', {
      name: sharedWorkerName || t('share.title'),
    }) as string;
    const desc = t('share.wechat_text_desc') as string;
    const text = `${title}\n\n${desc}\n\n${generatedUrl}`;
    const ok = await copyToClipboard(text);
    if (ok) {
      message.success(t('share.wechat_copied') || '微信分享文案已复制');
    } else {
      message.error(t('share.copy_failed') || '复制失败，请手动复制');
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

  // 物理删除（记录从数据库彻底移除）
  const handleDelete = async (shareId: number) => {
    if (!workerId) return;
    setRevokingId(shareId);
    try {
      await deleteShareToken(workerId, shareId);
      message.success(t('share.delete_success') || '已删除');
      fetchTokens();
    } catch (err: any) {
      // eslint-disable-next-line no-console
      console.error('删除分享 token 失败:', err);
      message.error(err?.message || t('share.delete_failed') || '删除失败');
    } finally {
      setRevokingId(null);
    }
  };

  // 重新上传远端（不重新生成 token，只重推）
  const handleRetryRemote = async (shareId: number) => {
    if (!workerId) return;
    setRevokingId(shareId);
    try {
      const res: any = await retryShareRemoteUpload(workerId, shareId);
      if (res?.short_url) {
        message.success(t('share.retry_remote_success') || '已重新发布到 quantcell.top');
      } else {
        message.warning(t('share.retry_remote_failed') || '重试失败');
      }
      fetchTokens();
    } catch (err: any) {
      // eslint-disable-next-line no-console
      console.error('重新上传分享失败:', err);
      message.error(err?.message || t('share.retry_remote_failed') || '重试失败');
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
        width: 200,
        render: (v: string, record: ShareTokenListItem) => (
          <Tooltip title={record.short_url || ''} placement="topLeft">
            <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
              {record.short_url
                ? record.short_url.replace(/^https?:\/\//, '').slice(0, 32) + (record.short_url.length > 40 ? '…' : '')
                : v}
            </span>
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
        width: 110,
        render: (_: any, record: ShareTokenListItem) => {
          const status = computeStatus(record);
          const meta = statusMeta(status);
          return <Tag color={meta.color}>{t(`share.${meta.key}`)}</Tag>;
        },
      },
      {
        title: t('share.remote_status_label') || '分发',
        key: 'remote_status',
        width: 140,
        align: 'center',
        render: (_: any, record: ShareTokenListItem) => {
          const r = record.remote_status;
          if (r === 'UPLOADED') return <Tag color="green">{t('share.remote_uploaded') || '已发布'}</Tag>;
          if (r === 'PENDING') return <Tag color="blue">{t('share.remote_pending') || '推送中'}</Tag>;
          if (r === 'FAILED') {
            return (
              <Tooltip title={record.remote_error || ''}>
                <Tag color="red">{t('share.remote_failed') || '推送失败'}</Tag>
              </Tooltip>
            );
          }
          if (r === 'REVOKED') return <Tag color="default">{t('share.remote_revoked') || '已撤销'}</Tag>;
          return <Tag>-</Tag>;
        },
      },
      {
        title: t('action'),
        key: 'action',
        width: 220,
        align: 'center',
        fixed: 'right',
        render: (_: any, record: ShareTokenListItem) => {
          const status = computeStatus(record);
          const revokeDisabled = status !== 'active';
          const canRetryRemote =
            record.remote_status === 'FAILED' &&
            !record.revoked;
          return (
            <Space size="small">
              {canRetryRemote && (
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  loading={revokingId === record.id}
                  onClick={() => handleRetryRemote(record.id)}
                >
                  {t('share.retry') || '重试'}
                </Button>
              )}
              <Popconfirm
                title={t('share.confirm_revoke')}
                onConfirm={() => handleRevoke(record.id)}
                okText={t('confirm')}
                cancelText={t('cancel')}
                disabled={revokeDisabled}
              >
                <Button
                  size="small"
                  icon={<StopOutlined />}
                  loading={revokingId === record.id}
                  disabled={revokeDisabled}
                >
                  {t('share.revoke')}
                </Button>
              </Popconfirm>
              <Popconfirm
                title={t('share.confirm_delete') || '确定要删除该分享链接？删除后无法恢复。'}
                onConfirm={() => handleDelete(record.id)}
                okText={t('confirm')}
                okButtonProps={{ danger: true }}
                cancelText={t('cancel')}
              >
                <Button
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  loading={revokingId === record.id}
                >
                  {t('share.delete') || '删除'}
                </Button>
              </Popconfirm>
            </Space>
          );
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
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
          {t('share.title')}
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={820}
      destroyOnClose
    >
      <Form layout="vertical">
        {/* 远端上传失败时给出非阻塞提示 */}
        {generatedUrl === '' && tokens.some((tk) => tk.remote_status === 'FAILED') && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message={t('share.remote_failed_hint') || '部分链接推送失败，可在列表中点击「重试」再次发布到 quantcell.top'}
          />
        )}

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

        {/* 生成的 URL 展示 + 复制 + 微信 + 二维码 */}
        <Form.Item>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              style={{ width: 'calc(100% - 330px)' }}
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
            <Tooltip title={t('share.copy_wechat_text') || '复制为微信分享文案'}>
              <Button
                type="default"
                icon={<WechatOutlined />}
                style={{ width: 110 }}
                disabled={!generatedUrl}
                onClick={handleCopyWechatText}
              >
                {t('share.wechat_share') || '微信'}
              </Button>
            </Tooltip>
            <Button
              type="default"
              icon={<DownloadOutlined />}
              style={{ width: 110 }}
              disabled={!generatedUrl}
              onClick={handleDownloadQR}
            >
              {t('share.qr_code') || '二维码'}
            </Button>
          </Space.Compact>
        </Form.Item>

        {/* 二维码预览（仅在有链接时显示） */}
        {generatedUrl && (
          <div ref={qrCanvasRef} style={{ display: 'flex', justifyContent: 'center', padding: '12px 0' }}>
            <QRCode
              value={generatedUrl}
              size={160}
              level="M"
              color="#000000"
              bgColor="#ffffff"
            />
          </div>
        )}
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
