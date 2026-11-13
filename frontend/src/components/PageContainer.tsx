/**
 * 页面容器组件
 * 功能：提供统一的页面布局结构
 * 使用方式：
 * <PageContainer title="页面标题">
 *   <div>页面内容</div>
 * </PageContainer>
 * <PageContainer title="详情标题" onBack={handleBack}>
 *   <div>详情页内容</div>
 * </PageContainer>
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
  /** 返回回调（可选）。提供后在标题左侧渲染统一的返回箭头，详情页统一用此入口，不再各自画返回按钮 */
  onBack?: () => void;
  /** 自定义类名 */
  className?: string;
}

/**
 * 页面容器组件
 * 提供统一的页面布局：外层 px-6 py-4 内边距，内容全宽铺满（不做限宽居中，
 * 否则宽屏下内容区与侧边栏之间会出现大片空白）。新页面请统一使用本容器。
 */
const PageContainer = ({ children, title, onBack, className = '' }: PageContainerProps) => {
  return (
    <div className={`flex flex-col px-6 py-4 ${className}`}>
      {/* 页面标题区域：返回按钮与标题同行、同一底部间距，保证各页面标题行几何一致 */}
      {(title || onBack) && (
        <div className="mb-6 flex shrink-0 items-center gap-1">
          {onBack && (
            <Button
              type="text"
              aria-label="back"
              icon={<ArrowLeftOutlined />}
              onClick={onBack}
            />
          )}
          {title && (
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{title}</h1>
          )}
        </div>
      )}

      {/* 页面内容区域（全宽） */}
      {children}
    </div>
  );
};

export default PageContainer;
