/**
 * 因子「缺数据守卫」（分析 / 对比两个页签共享）：
 * - 提交前预检本地 Parquet（backtestApi.precheckData，仅文件存在性检查）；
 * - 缺数据 → 弹窗列出 品种 · 周期，确认后创建下载任务并轮询（交互复用回测预检弹窗）；
 * - 下载完成后 onContinue 让调用方用保存的参数直接续跑（不重跑预检，避免死循环）；
 * - 失败 / 超时（10 分钟）在弹窗内给出重试按钮与「数据管理」引导，不自动续跑。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { App as AntApp, Button, Modal, Progress, Space, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import dayjs, { type Dayjs } from 'dayjs';
import { backtestApi } from '@/api';
import { dataApi } from '@/api/dataApi';

const POLL_MS = 2000;
const TIMEOUT_MS = 10 * 60 * 1000;

type RangeVal = [Dayjs, Dayjs] | null | undefined;

interface MissingItem {
  symbol: string;
  interval: string;
}

interface SymbolProgress {
  symbol: string;
  interval: string;
  percentage: number;
  status: string;
}

// 后端缺数据报错文案固定为中文（不受 UI 语言影响，不能用 t() 匹配）：
// 「未找到 BNBUSDT 1h 的Parquet文件」——CJK 用 unicode 转义以通过 i18n 硬编码审计
const MISSING_MSG_RE = /\u672a\u627e\u5230\s+(\S+)\s+(\S+)\s+\u7684Parquet\u6587\u4ef6/;

/** 命中后端「未找到 BNBUSDT 1h 的Parquet文件」类报错，解析出 symbol / interval */
export const parseMissingDataMsg = (msg: string): MissingItem | null => {
  const m = MISSING_MSG_RE.exec(msg || '');
  return m ? { symbol: m[1], interval: m[2] } : null;
};

export function useFactorDataGuard(options: { onContinue?: () => void } = {}) {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [missing, setMissing] = useState<MissingItem[]>([]);
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState('');
  const [symProgress, setSymProgress] = useState<SymbolProgress[]>([]);
  const [downloadError, setDownloadError] = useState('');
  // 本次下载是否用的是默认范围（表单未填时间范围 → 默认最近 1 年），用于弹窗小字提示
  const [defaultRange, setDefaultRange] = useState(false);

  const onContinueRef = useRef(options.onContinue);
  onContinueRef.current = options.onContinue;
  const rangeRef = useRef<RangeVal>(null);
  // 市场类型：因子页固定 spot，研究抽屉按表单的 spot/future 传进来（下载与预检必须同口径）
  const candleRef = useRef<'spot' | 'future'>('spot');
  const cancelRef = useRef<{ aborted: boolean } | null>(null);

  // 卸载时中止前端轮询；后台下载任务不受影响
  useEffect(() => () => {
    if (cancelRef.current) cancelRef.current.aborted = true;
  }, []);

  const show = useCallback((items: MissingItem[], range: RangeVal, candleType: 'spot' | 'future') => {
    rangeRef.current = range ?? null;
    candleRef.current = candleType;
    setDefaultRange(!range || !range.length);
    setMissing(items);
    setDownloadError('');
    setOpen(true);
  }, []);

  /** 提交前预检。true = 数据齐备（或预检失败降级，按旧流程直接跑）；false = 已弹窗等用户确认 */
  const ensureData = useCallback(
    async (
      symbols: string[],
      intervals: string[],
      range?: RangeVal,
      candleType: 'spot' | 'future' = 'spot',
    ) => {
      try {
        const pre = await backtestApi.precheckData({ symbols, intervals, candle_type: candleType });
        if (pre.all_available || !pre.missing?.length) return true;
        show(pre.missing, range, candleType);
        return false;
      } catch (e) {
        console.warn('[useFactorDataGuard] data precheck failed, skip guard:', e);
        return true;
      }
    },
    [show],
  );

  /** job 报错命中「未找到 … Parquet」时调用：按表单参数补全缺失清单（预检失败退回报错解析到的一对） */
  const openFromError = useCallback(
    async (
      found: MissingItem,
      symbols: string[],
      intervals: string[],
      range?: RangeVal,
      candleType: 'spot' | 'future' = 'spot',
    ) => {
      let items = [found];
      try {
        const pre = await backtestApi.precheckData({
          symbols: symbols.length ? symbols : [found.symbol],
          intervals: intervals.length ? intervals : [found.interval],
          candle_type: candleType,
        });
        if (!pre.all_available && pre.missing?.length) items = pre.missing;
      } catch {
        /* 保留报错解析结果 */
      }
      show(items, range, candleType);
    },
    [show],
  );

  /** 弹窗确认：创建下载任务并轮询。取消只中止前端轮询，后台任务继续 */
  const startDownload = async () => {
    const symbols = [...new Set(missing.map((m) => m.symbol))];
    const intervals = [...new Set(missing.map((m) => m.interval))];
    // 时间范围：表单填了就用（YYYY-MM-DD）；没填默认最近 1 年
    const [start, end] = rangeRef.current?.length
      ? [rangeRef.current[0].format('YYYY-MM-DD'), rangeRef.current[1].format('YYYY-MM-DD')]
      : [dayjs().subtract(1, 'year').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')];

    setDownloading(true);
    setDownloadError('');
    setProgress(0);
    setSymProgress([]);
    setProgressMsg(t('factor_download_creating'));
    cancelRef.current = { aborted: false };

    try {
      const res: any = await dataApi.downloadCryptoData({
        symbols,
        interval: intervals,
        start,
        end,
        candle_type: candleRef.current,
        mode: 'inc',
        exchange: 'binance',
      });
      const taskId = res?.task_id || res?.data?.task_id;
      if (!taskId) throw new Error(t('factor_download_task_no_id'));

      setProgressMsg(t('factor_download_in_progress'));
      const startedAt = Date.now();
      let done = false;
      let failed = false;
      while (Date.now() - startedAt < TIMEOUT_MS) {
        if (cancelRef.current?.aborted) return;
        await new Promise((r) => setTimeout(r, POLL_MS));
        let info: any = null;
        try {
          const status: any = await dataApi.getTaskStatus(taskId);
          info = status?.task_info || status;
        } catch {
          continue; // 单次状态查询失败忽略（网络抖动），靠超时兜底
        }
        // 逐品种进度: 后端 symbols_progress 是 { task_key: {symbol, interval, percentage, status} }
        const list: SymbolProgress[] = Object.values(info?.symbols_progress || {}).map((p: any) => ({
          symbol: p.symbol,
          interval: p.interval,
          percentage: Number(p.percentage || 0),
          status: p.status || 'running',
        }));
        setSymProgress(list);
        // ponytail: 总体进度 = 已完成品种数 / 总品种数，沿用回测页口径，避免单品种 percentage 反复 0→100 跳变
        const total = list.length || symbols.length;
        const completed = list.filter((p) => p.status === 'completed').length;
        setProgress(total ? Math.round((completed / total) * 100) : 0);

        if (info?.status === 'completed') {
          done = true;
          break;
        }
        if (info?.status === 'failed') {
          failed = true;
          setDownloadError(t('factor_download_failed', { msg: info?.error || info?.message || t('unknown_error') }));
          break;
        }
      }
      if (cancelRef.current?.aborted) return;
      if (done) {
        setOpen(false);
        message.success(t('factor_download_success_continue'));
        onContinueRef.current?.();
      } else if (!failed) {
        setDownloadError(t('factor_download_timeout'));
      }
    } catch (e) {
      setDownloadError(t('factor_download_failed', { msg: (e as Error)?.message || t('unknown_error') }));
    } finally {
      setDownloading(false);
    }
  };

  const handleCancel = () => {
    if (downloading && cancelRef.current) {
      cancelRef.current.aborted = true; // 只中止前端轮询，后台下载任务继续
      message.info(t('factor_download_cancelled_hint'));
    }
    setOpen(false);
    setDownloading(false);
  };

  const guardModal: ReactNode = (
    <Modal
      title={t('factor_missing_title')}
      open={open}
      zIndex={1100}
      onCancel={handleCancel}
      width={560}
      footer={downloading
        ? [<Button key="cancel" onClick={handleCancel}>{t('cancel')}</Button>]
        : [
            <Button key="cancel" onClick={() => setOpen(false)}>{t('cancel')}</Button>,
            <Button key="download" type="primary" onClick={startDownload}>
              {downloadError ? t('factor_download_retry') : t('factor_download_and_continue')}
            </Button>,
          ]}
    >
      <Space orientation="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
        <div>{t('factor_missing_desc', { n: missing.length })}</div>
        <div style={{ maxHeight: 240, overflowY: 'auto', border: '1px solid var(--tw-color-border-secondary)', borderRadius: 6, padding: 12 }}>
          <Space wrap size={[8, 8]}>
            {missing.map((m, i) => (
              <Tag key={`${m.symbol}-${m.interval}-${i}`} color="orange" style={{ fontFamily: 'monospace' }}>
                {m.symbol} · {m.interval}
              </Tag>
            ))}
          </Space>
        </div>
        {downloading && (
          <>
            <Progress percent={progress} status="active" />
            <div style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 60%, transparent)', fontSize: 13 }}>{progressMsg}</div>
            {/* 逐品种下载进度: 已完成品种绿色背景（与回测预检弹窗同款） */}
            {symProgress.length > 0 && (
              <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid var(--tw-color-border-secondary)', borderRadius: 6 }}>
                {symProgress.map((p) => {
                  const done = p.status === 'completed';
                  return (
                    <div
                      key={`${p.symbol}-${p.interval}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 12px',
                        borderBottom: '1px solid var(--tw-color-border-secondary)',
                        background: done ? 'color-mix(in srgb, var(--tw-color-success) 8%, var(--tw-color-background))' : undefined,
                      }}
                    >
                      <span style={{ fontFamily: 'monospace', fontSize: 13 }}>
                        {p.symbol} · {p.interval}
                      </span>
                      <span style={{ fontSize: 12, color: done ? 'var(--tw-color-success)' : 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }}>
                        {done ? t('factor_download_completed') : `${p.percentage}%`}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
        {downloadError && <div style={{ color: 'var(--tw-color-error)', fontSize: 13 }}>{downloadError}</div>}
        {defaultRange && (
          <div style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)', fontSize: 12 }}>
            {t('factor_download_range_default')}
          </div>
        )}
        <div style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)', fontSize: 12 }}>
          {t('factor_missing_goto_before')}
          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => { setOpen(false); navigate('/data-management'); }}>
            {t('factor_missing_data_management')}
          </Button>
          {t('factor_missing_goto_after')}
        </div>
      </Space>
    </Modal>
  );

  return { guardModal, ensureData, openFromError };
}
