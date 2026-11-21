/* eslint-disable react-refresh/only-export-components -- FILLABLE_KINDS / probeMarkets / groupSymbolsByMarket 是纯函数，导出给单测直接跑 */
/**
 * 数据管理首屏两块只读卡：数据源水位（4 张）+ 存储用量（demo #view-data 1979-2047）
 *
 * 数据源：GET /api/v1/data/archive/watermark（backend/collector/api/archive.py）
 * - 水位 = 各 (market, kind, symbol) 的 `_meta.json` 按 kind 求和 / 取 min-max 日期
 * - 存储 = 各 kind 下 .parquet 文件体积之和
 * 只表达真实两态：有数据 / 无数据（dot 颜色 = 有数据时按落后天数分 绿 / 黄）；
 * 落后 N 天 = 今天 − latest_date（日期粒度，无小时）；demo 的「限频/断连/排队」无源，不造。
 *
 * 「补齐」钮（卡底）：对该 kind **已采集**的 symbols 按 market 分组各发一个
 * POST /data/archive/download（mode='inc'，start_date = 该 kind 的 latest_date，end_date = 今天）。
 * 没有已采集 symbols / 没有 latest_date / 归档端点不认的 kind（kline、fundingRate 走数据池
 * 下载路径，不在 /archive 端点值域内）一律不显示钮 —— 点了也只会 400，是假动作。
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { App, Button, Card, Select } from 'antd';

import { dataApi } from '@/api/dataApi';
import type { ArchiveWatermarkResponse } from '@/api/dataApi';
import { archiveApi } from '@/api/archiveApi';
import { ARCHIVE_INTERVALS, ARCHIVE_KINDS, FUTURES_ONLY_KINDS, INTERVAL_REQUIRED_KINDS } from '@/types/data';
import type { ArchiveKind, DataKind, MarketType } from '@/types/data';

// 首屏固定四张水位卡（demo 口径）；接口里没有该 kind 时渲染弱态「无数据」，不补 0
const WATERMARK_KINDS = ['kline', 'fundingRate', 'markPriceKlines', 'aggTrades'] as const;

const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';

/** 归档下载端点只认 7 个 ArchiveKind（kline / fundingRate 是数据池路径的 kind） */
export const FILLABLE_KINDS = new Set<string>(ARCHIVE_KINDS);

/** 需要 interval 的 kind（后端要求必须在 8 个周期内，缺省给 1h） */
export const FILL_DEFAULT_INTERVAL = '1h';

/** 待下发的一个 market 分组（同 kind 不同 market 必须分开发任务） */
export interface FillGroup {
  market: MarketType;
  symbols: string[];
}

/** 探哪些 market：期货专属 kind 在 spot 上必空，不必白探一次 */
export function probeMarkets(kind: string): MarketType[] {
  return FUTURES_ONLY_KINDS.includes(kind as DataKind) ? ['um', 'cm'] : ['spot', 'um', 'cm'];
}

/**
 * 各 market 已采集 symbols → 待下发分组。
 * 空列表 / 探测失败（null）的 market 直接丢弃：没有可补之物就不发任务。
 */
export function groupSymbolsByMarket(
  probes: Array<{ market: MarketType; symbols: string[] | null }>,
): FillGroup[] {
  return probes
    .filter((probe) => (probe.symbols?.length ?? 0) > 0)
    .map((probe) => ({ market: probe.market, symbols: [...(probe.symbols ?? [])] }));
}


// 累计量：< 100 万走千分位整数，≥ 100 万走紧凑写法（与 demo「8.42M」同形制）
function formatCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0';
  if (n < 1_000_000) return Math.round(n).toLocaleString('en-US');
  const units: Array<[number, string]> = [
    [1e9, 'B'],
    [1e6, 'M'],
  ];
  const [size, suffix] = units.find(([size]) => n >= size) ?? [1e6, 'M'];
  return `${(n / size).toFixed(2)}${suffix}`;
}

// 体积：GB/TB 为主（demo 口径），小目录落到 KB/MB
function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${index === 0 || value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

// 今天 − latest_date（天）；latest_date 为日粒度 YYYY-MM-DD
function lagDays(latest: string): number {
  return dayjs().startOf('day').diff(dayjs(latest).startOf('day'), 'day');
}

export default function ArchiveWatermarkStrip() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [data, setData] = useState<ArchiveWatermarkResponse | null>(null);
  const [failed, setFailed] = useState(false);
  // 各 kind 分 market 的待补分组（只含已采集 symbols 的 market）
  const [fills, setFills] = useState<Record<string, FillGroup[]>>({});
  // 补齐按钮 loading（按 kind）
  const [fillingKind, setFillingKind] = useState<string | null>(null);
  // K 线类 kind 的补齐周期（默认 1h，仅该 kind 需要 interval）
  const [fillInterval, setFillInterval] = useState<Record<string, string>>({});
  // 补齐成功后重新拉水位 + 重探 symbols（下载是异步任务，不本地假造已完成）
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let alive = true;
    dataApi
      .getArchiveWatermark()
      .then((res) => {
        if (alive) {
          setData(res);
          setFailed(false);
        }
      })
      .catch(() => {
        if (alive) setFailed(true);
      });

    // 探测各 kind 已采集 symbols：决定「补齐」钮出不出现，以及按 market 分别下发
    const kinds = WATERMARK_KINDS.filter((kind) => FILLABLE_KINDS.has(kind));
    Promise.all(
      kinds.map(async (kind) => {
        const probes = await Promise.all(
          probeMarkets(kind).map(async (market) => {
            try {
              const resp = await archiveApi.listSymbols(kind as ArchiveKind, market);
              return { market, symbols: Array.isArray(resp?.symbols) ? resp.symbols : [] };
            } catch {
              // 单个 market 探测失败按「无数据」处理：宁可少一个钮，也不发注定失败的任务
              return { market, symbols: null };
            }
          }),
        );
        return [kind, groupSymbolsByMarket(probes)] as const;
      }),
    ).then((entries) => {
      if (alive) setFills(Object.fromEntries(entries));
    });

    return () => {
      alive = false;
    };
  }, [reloadKey]);

  // 补齐：该 kind 每个 market 一个增量任务（start = 该 kind 的 latest_date，end = 今天）
  const handleFill = async (kind: string, latest: string) => {
    const groups = fills[kind] ?? [];
    if (groups.length === 0) return;
    setFillingKind(kind);
    const needsInterval = INTERVAL_REQUIRED_KINDS.includes(kind as DataKind);
    const interval = needsInterval ? (fillInterval[kind] ?? FILL_DEFAULT_INTERVAL) : undefined;
    const endDate = dayjs().format('YYYY-MM-DD');
    const taskIds: string[] = [];
    const errors: string[] = [];
    for (const group of groups) {
      try {
        const resp = await archiveApi.downloadTask({
          symbols: group.symbols,
          kind: kind as ArchiveKind,
          market: group.market,
          start_date: latest,
          end_date: endDate,
          mode: 'inc',
          interval,
        });
        if (resp?.task_id) taskIds.push(resp.task_id);
        else errors.push(`${group.market}: ${resp?.message ?? 'no task_id'}`);
      } catch (error) {
        // 后端 message 原样展示（不翻译、不改写）
        errors.push(error instanceof Error ? error.message : String(error));
      }
    }
    if (taskIds.length > 0) {
      message.success(t('dm_wm_fill_started', { n: taskIds.length, tasks: taskIds.join(', ') }));
    }
    errors.forEach((err) => message.error(err));
    setFillingKind(null);
    setReloadKey((key) => key + 1);
  };

  if (failed) {
    return (
      <div className="qc-card-sub" style={{ marginBottom: 12 }}>
        {t('dm_wm_load_failed')}
      </div>
    );
  }

  // 首屏请求未落地前不渲染「无数据 / 合计 0 B」（那是加载态，不是真实结论）
  if (data === null) {
    return (
      <div className="qc-card-sub" style={{ marginBottom: 12 }}>
        {t('dm_loading')}
      </div>
    );
  }

  const watermarks = data.watermarks;
  const storage = [...data.storage].sort((a, b) => b.bytes - a.bytes);
  const totalBytes = data.total_bytes;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 12 }}>
      <div className="qc-kpi-grid">
        {WATERMARK_KINDS.map((kind) => {
          const wm = watermarks.find((item) => item.kind === kind);
          const latest = wm?.latest_date ?? null;
          const lag = latest ? lagDays(latest) : null;
          const hasData = Boolean(wm && latest);
          const dotColor = !hasData
            ? 'var(--qc-text-quaternary)'
            : lag !== null && lag > 1
              ? 'var(--qc-warning)'
              : 'var(--qc-success)';
          // kline / markPriceKlines 的 total_rows 是 bar 数，其余 kind 是条目数
          const isBar = kind === 'kline' || kind.endsWith('Klines');
          const groups = fills[kind] ?? [];
          // 无已采集 symbols / 无水位 / 端点不认的 kind → 不显示补齐钮（无可补之物）
          const canFill = Boolean(latest) && groups.length > 0 && FILLABLE_KINDS.has(kind);
          const needsInterval = INTERVAL_REQUIRED_KINDS.includes(kind as DataKind);
          return (
            <div className="qc-kpi" key={kind}>
              <div className="qc-kpi-top">
                <span className="qc-kpi-lb" style={{ fontFamily: MONO }}>
                  {kind}
                </span>
                <i
                  aria-hidden
                  style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor }}
                />
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'space-between',
                  gap: 8,
                  marginTop: 7,
                }}
              >
                <span className="qc-kpi-lb">{isBar ? t('dm_wm_unit_bar') : t('dm_wm_unit_rows')}</span>
                <span
                  className="qc-kpi-num"
                  style={{
                    marginTop: 0,
                    fontSize: hasData ? 22 : 14,
                    color: hasData ? undefined : 'var(--qc-text-quaternary)',
                  }}
                >
                  {hasData ? formatCount(wm?.total_rows ?? 0) : t('dm_wm_no_data')}
                </span>
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  marginTop: 5,
                }}
              >
                <span className="qc-kpi-sub" style={{ marginTop: 0 }}>
                  {t('dm_wm_latest')}{' '}
                  <span className="qc-mono">{latest ?? '—'}</span>
                </span>
                {hasData ? (
                  <span className={`qc-chip ${lag !== null && lag > 1 ? 'warn' : 'ok'}`}>
                    {lag !== null && lag > 1
                      ? t('dm_wm_lag_n', { n: lag })
                      : t('dm_wm_lag_fresh')}
                  </span>
                ) : (
                  <span className="qc-chip quiet">{t('dm_wm_no_data')}</span>
                )}
              </div>
              {hasData && (
                <div
                  className="qc-kpi-sub"
                  style={{
                    marginTop: 4,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 6,
                  }}
                >
                  <span>{t('dm_wm_symbols_n', { n: wm?.symbol_count ?? 0 })}</span>
                  {canFill && (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                      {needsInterval && (
                        <Select
                          size="small"
                          value={fillInterval[kind] ?? FILL_DEFAULT_INTERVAL}
                          onChange={(value) =>
                            setFillInterval((prev) => ({ ...prev, [kind]: value }))
                          }
                          options={ARCHIVE_INTERVALS.map((value) => ({ value, label: value }))}
                          style={{ width: 62, fontSize: 11 }}
                          aria-label={t('dm_wm_fill_interval')}
                        />
                      )}
                      <Button
                        type="link"
                        size="small"
                        loading={fillingKind === kind}
                        onClick={() => handleFill(kind, latest as string)}
                        style={{ padding: 0, height: 'auto', fontSize: 11 }}
                      >
                        {t('dm_wm_fill')}
                      </Button>
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Card
        className="qc-card"
        title={t('dm_wm_storage_title')}
        extra={
          <span className="qc-card-sub">
            {t('dm_wm_storage_total')}{' '}
            <span className="qc-mono" style={{ color: 'var(--qc-text)' }}>
              {formatBytes(totalBytes)}
            </span>
          </span>
        }
      >
        {storage.length === 0 ? (
          <div className="qc-card-sub">{t('dm_wm_storage_empty')}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {storage.map((item) => {
              const pct = totalBytes > 0 ? (item.bytes / totalBytes) * 100 : 0;
              return (
                <div key={item.kind} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span
                    className="qc-card-sub"
                    style={{ width: 150, flex: '0 0 150px', color: 'var(--qc-text-tertiary)' }}
                    title={item.kind}
                  >
                    {item.kind} · parquet
                  </span>
                  <span
                    aria-hidden
                    style={{
                      flex: 1,
                      height: 6,
                      borderRadius: 3,
                      background: 'var(--qc-border)',
                      overflow: 'hidden',
                    }}
                  >
                    <i
                      style={{
                        display: 'block',
                        height: '100%',
                        width: `${Math.max(pct, 1)}%`,
                        borderRadius: 3,
                        background: 'var(--qc-primary)',
                      }}
                    />
                  </span>
                  <span
                    className="qc-mono"
                    style={{
                      width: 78,
                      flex: '0 0 78px',
                      textAlign: 'right',
                      color: 'var(--qc-text-secondary)',
                    }}
                  >
                    {formatBytes(item.bytes)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
