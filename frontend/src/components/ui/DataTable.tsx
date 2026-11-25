/**
 * DataTable - 全站列表表格原语（design-spec §6.5 / §6.7 / §6.13）
 *
 * 包一层 antd Table，统一「qc-table」类名与 qc- 密度口径：
 * - size="small"、横向滚动 scroll={{x:'max-content'}}（列多时外层出滚动条）
 * - 空态渲染 §6.13 的 .qc-empty（图标块 46×46 + 主文案 + 说明），不再是 antd 灰图
 * - 分页条按 §6.7 自绘：外包 .qc-pg-bar（1px 上边线 + margin-top 12 + padding-top 9），
 *   左侧 .qc-pg-info =「共 N 条 · 每页 [▾]」，右侧页码（28px 钮 / 当前页 primary tint）
 *   + 「跳至 [__] 页」；页码算法 showLessItems（首尾常显 + 当前页 ±1，如 1 … 3 4 5 … 9），
 *   省略号经 itemRender 渲染为非交互 span（规范要求）
 *   档位体系取自页面传入的 pageSizeOptions（缺省 PER_PAGE_OPTIONS，12 的倍数对齐
 *   卡片网格，是既有决策，不要改成 10/20/50）
 *
 * 业务语义（列定义、选中、行事件、分页 onChange）全部透传 antd TableProps。
 */
import { useMemo } from 'react';
import { Pagination, Select, Table } from 'antd';
import type { TablePaginationConfig, TableProps } from 'antd';
import { DatabaseOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { PER_PAGE_OPTIONS } from '../../constants/pagination';

/** §6.13 空态：图标块 + 主文案 + 说明（独立导出，卡片视图等非表格场景也可用） */
export function QcEmpty({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title?: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="qc-empty">
      <div className="qc-empty-ico">{icon ?? <DatabaseOutlined />}</div>
      {title && <p className="qc-empty-t">{title}</p>}
      {description && <p className="qc-empty-h">{description}</p>}
      {action}
    </div>
  );
}

export interface DataTableProps<T extends object> extends Omit<TableProps<T>, 'pagination'> {
  /** 追加到 qc-table 之后的类名 */
  className?: string;
  /** 空态图标（默认 DatabaseOutlined） */
  emptyIcon?: React.ReactNode;
  /** 空态主文案（缺省 i18n「暂无数据」） */
  emptyTitle?: string;
  /** 空态说明文案（可省） */
  emptyDescription?: string;
  /** 空态操作按钮（可省） */
  emptyAction?: React.ReactNode;
  /** §6.7 自绘分页条配置；false 关闭分页。翻页走 cfg.onChange(page, pageSize) */
  pagination?: TablePaginationConfig | false;
  /** 数据已按页裁好（服务端分页）时不再二次切片 */
  remote?: boolean;
}

const DataTable = <T extends object>({
  className,
  emptyIcon,
  emptyTitle,
  emptyDescription,
  emptyAction,
  pagination,
  remote,
  dataSource,
  locale,
  scroll,
  ...rest
}: DataTableProps<T>) => {
  const { t } = useTranslation();

  // —— §6.7 分页条口径 ——
  // total：服务端分页由页面传入；本地分页按 dataSource 全量算
  const cfg = pagination === false ? null : (pagination ?? null);
  const total = cfg ? (typeof cfg.total === 'number' ? cfg.total : (dataSource?.length ?? 0)) : 0;
  const pageSize = Math.max(1, Number(cfg?.pageSize) || 12);
  // 当前页越界钳制（切档位/筛掉数据后 current 可能超出最大页）
  const maxPage = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(1, Number(cfg?.current) || 1), maxPage);

  // 本地分页切片；remote（服务端已裁页）原样透传
  const pagedDataSource = useMemo(() => {
    if (remote || !cfg) return dataSource;
    const start = (current - 1) * pageSize;
    return dataSource?.slice(start, start + pageSize);
  }, [remote, cfg, current, pageSize, dataSource]);

  const firePageChange = (page: number, size: number) => {
    const clamped = Math.min(Math.max(1, page), Math.max(1, Math.ceil(total / size)));
    cfg?.onChange?.(clamped, size);
  };

  const mergedLocale = useMemo(() => {
    if (locale?.emptyText) return locale;
    return {
      ...locale,
      emptyText: (
        <QcEmpty
          icon={emptyIcon}
          title={emptyTitle ?? t('no_data')}
          description={emptyDescription}
          action={emptyAction}
        />
      ),
    };
  }, [locale, emptyIcon, emptyTitle, emptyDescription, emptyAction, t]);

  const showPageSizeSelect = cfg?.showSizeChanger !== false && cfg !== null;
  const sizeOptions = (cfg?.pageSizeOptions ?? PER_PAGE_OPTIONS).map(Number);

  return (
    <>
      <Table<T>
        size="small"
        className={`qc-table${className ? ` ${className}` : ''}`}
        dataSource={pagedDataSource}
        scroll={scroll ?? { x: 'max-content' }}
        pagination={false}
        locale={mergedLocale}
        {...rest}
      />
      {cfg && (
        <div className="qc-pg-bar">
          <div className="qc-pg-info">
            <span>{t('total_items', { total })}</span>
            {showPageSizeSelect && (
              <>
                <span className="qc-pg-sep">·</span>
                <span>{t('per_page')}</span>
                <Select
                  size="small"
                  className="qc-pg-size"
                  value={pageSize}
                  onChange={(size) => firePageChange(current, size)}
                  options={sizeOptions.map((n) => ({ value: n, label: String(n) }))}
                  popupMatchSelectWidth={false}
                />
              </>
            )}
          </div>
          <Pagination
            size="small"
            className="qc-pagination"
            showLessItems
            showQuickJumper
            showSizeChanger={false}
            current={current}
            pageSize={pageSize}
            total={total}
            onChange={firePageChange}
            itemRender={(_page, type, node) =>
              type === 'jump-prev' || type === 'jump-next' ? (
                <span className="qc-pg-ellipsis">…</span>
              ) : (
                node
              )
            }
          />
        </div>
      )}
    </>
  );
};

export default DataTable;
