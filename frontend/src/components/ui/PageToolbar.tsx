/**
 * PageToolbar - 列表页工具栏原语（design-spec §6.6）
 *
 * 布局：搜索框（32px/8px 圆角，占位 --qc-text-quaternary）→ 过滤插槽
 * （chips / selects）→ 右侧计数（mono 11px「显示 x-y / 共 z」）→ 右侧操作插槽。
 * 过滤与分页联动的「过滤后页码归 1」由页面自行处理。
 *
 * 各插槽均可选；filters/actions 接任意 ReactNode，chip/select 细节归页面对齐 §6.2。
 */
import type { ChangeEvent, KeyboardEvent, ReactNode } from 'react';
import { Input } from 'antd';

export interface ToolbarSearchConfig {
  value: string;
  /** 受控输入；页面在 onChange 里做过滤（并按 §6.6 把页码归 1） */
  onChange: (value: string) => void;
  placeholder: string;
  /** 回车提交（服务端过滤列表用）；不传则纯受控输入 */
  onPressEnter?: (value: string) => void;
  ariaLabel?: string;
}

export interface PageToolbarProps {
  /** 搜索框配置；不传则不渲染 */
  search?: ToolbarSearchConfig;
  /** 中部过滤插槽（chips / selects） */
  filters?: ReactNode;
  /** 右侧计数文案，如「显示 1-12 / 共 24」 */
  count?: ReactNode;
  /** 右侧操作插槽（按钮组） */
  actions?: ReactNode;
  className?: string;
}

const PageToolbar = ({ search, filters, count, actions, className }: PageToolbarProps) => {
  const handlePressEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    const el = e.currentTarget;
    // 回车提交后失焦，避免弹层/刷新时焦点残留在输入框
    el.blur();
    search?.onPressEnter?.(el.value);
  };

  return (
    <div className={`qc-toolbar${className ? ` ${className}` : ''}`}>
      {search && (
        <Input
          className="qc-tsearch"
          value={search.value}
          placeholder={search.placeholder}
          aria-label={search.ariaLabel ?? search.placeholder}
          allowClear
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            // 点 clear 清空时也走同一入口，页面据此归位页码/重发请求
            search.onChange(e.target.value);
          }}
          onPressEnter={handlePressEnter}
        />
      )}
      {filters && <div className="qc-toolbar-filters">{filters}</div>}
      {count && <span className="qc-toolbar-count">{count}</span>}
      {actions && <div className="qc-toolbar-actions">{actions}</div>}
    </div>
  );
};

export default PageToolbar;
