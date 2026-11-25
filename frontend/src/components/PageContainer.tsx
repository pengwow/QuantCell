/**
 * 页面容器组件 —— design-spec §5 page-head
 * 结构：page-head（返回 + 标题 16px/650 + 副标 11px + 右侧操作区）+ 内容
 * 使用方式：
 * <PageContainer title="页面标题">
 *   <div>页面内容</div>
 * </PageContainer>
 * <PageContainer title="详情标题" onBack={handleBack}>…</PageContainer>
 * <PageContainer title="列表" subtitle="口径行" actions={<Button/>}>…</PageContainer>
 */
import { ReactNode } from 'react';
import { Button } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';

// 页面容器属性接口
export interface PageContainerProps {
  /** 子元素 */
  children: ReactNode;
  /** 页面标题（可选） */
  title?: string;
  /** 副标（可选）：mono 11px 数据口径行（§5 page-sub） */
  subtitle?: string;
  /** 标题右侧同位元素（可选）：demo 里的版本 chip 等，与标题同一基线、间距 10px */
  titleExtra?: ReactNode;
  /** 右侧操作区（可选）：按钮组，gap 8px（§5 page-actions） */
  actions?: ReactNode;
  /** 返回回调（可选）。提供后在标题左侧渲染统一的返回箭头，详情页统一用此入口，不再各自画返回按钮 */
  onBack?: () => void;
  /** 自定义类名 */
  className?: string;
}

/**
 * 页面容器组件
 * 外边距由布局层（.qc-main 4/4/18）与 page-head（2/2/14）提供，容器自身不再
 * 叠加水平内边距（模拟 demo：app-body 12 + main 4 + page-head margin 2 ≈ 16px 视觉边距）。
 * 新页面请统一使用本容器。
 */
const PageContainer = ({ children, title, subtitle, titleExtra, actions, onBack, className = '' }: PageContainerProps) => {
  const hasHead = Boolean(title || subtitle || actions || onBack);

  return (
    <div className={`flex min-w-0 flex-col ${className}`}>
      {/* page-head：返回按钮与标题同行、同一底部间距，保证各页面标题行几何一致 */}
      {hasHead && (
        <div className="qc-page-head">
          <div className="flex min-w-0 items-center gap-1">
            {onBack && (
              <Button
                type="text"
                aria-label="back"
                icon={<ArrowLeftOutlined />}
                onClick={onBack}
              />
            )}
            <div className="min-w-0">
              {titleExtra ? (
                <div className="flex min-w-0 items-center gap-[10px]">
                  {title && <h1 className="qc-page-title">{title}</h1>}
                  {titleExtra}
                </div>
              ) : (
                title && <h1 className="qc-page-title">{title}</h1>
              )}
              {subtitle && <p className="qc-page-sub">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="qc-page-actions">{actions}</div>}
        </div>
      )}

      {/* 页面内容区域（全宽） */}
      {children}
    </div>
  );
};

export default PageContainer;
