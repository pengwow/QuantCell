/**
 * 数据管理首屏两块只读卡：数据源水位（4 张）+ 存储用量（demo #view-data 1979-2047）
 *
 * 数据源：GET /api/v1/data/archive/watermark（backend/collector/api/archive.py）
 * - 水位 = 各 (market, kind, symbol) 的 `_meta.json` 按 kind 求和 / 取 min-max 日期
 * - 存储 = 各 kind 下 .parquet 文件体积之和
 * 只表达真实两态：有数据 / 无数据（dot 颜色 = 有数据时按落后天数分 绿 / 黄）；
 * 落后 N 天 = 今天 − latest_date（日期粒度，无小时）；demo 的「限频/断连/排队」无源，不造。
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { Card } from 'antd';

import { dataApi } from '@/api/dataApi';
import type { ArchiveWatermarkResponse } from '@/api/dataApi';

// 首屏固定四张水位卡（demo 口径）；接口里没有该 kind 时渲染弱态「无数据」，不补 0
const WATERMARK_KINDS = ['kline', 'fundingRate', 'markPriceKlines', 'aggTrades'] as const;

const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';

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
  const [data, setData] = useState<ArchiveWatermarkResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    dataApi
      .getArchiveWatermark()
      .then((res) => {
        if (alive) setData(res);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

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
                <div className="qc-kpi-sub" style={{ marginTop: 4 }}>
                  {t('dm_wm_symbols_n', { n: wm?.symbol_count ?? 0 })}
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
