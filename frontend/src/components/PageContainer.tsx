/**
 * 页面容器组件
 * 功能：提供统一的页面布局结构
 * 使用方式：
 * <PageContainer title="页面标题">
 *   <div>页面内容</div>
 * </PageContainer>
 */
import { ReactNode } from 'react';

// 页面容器属性接口
export interface PageContainerProps {
  /** 子元素 */
  children: ReactNode;
  /** 页面标题（可选） */
  title?: string;
  /** 自定义类名 */
  className?: string;
}

/**
 * 页面容器组件
 * 提供统一的页面布局：外层 px-6 py-4 内边距，内容全宽铺满（不做限宽居中，
 * 否则宽屏下内容区与侧边栏之间会出现大片空白）。新页面请统一使用本容器。
 */
const PageContainer = ({ children, title, className = '' }: PageContainerProps) => {
  return (
    <div className={`flex flex-col px-6 py-4 ${className}`}>
      {/* 页面标题区域 */}
      {title && (
        <h1 className="mb-6 shrink-0 text-2xl font-semibold text-gray-900 dark:text-gray-100">
          {title}
        </h1>
      )}

      {/* 页面内容区域（全宽） */}
      {children}
    </div>
  );
};

export default PageContainer;
