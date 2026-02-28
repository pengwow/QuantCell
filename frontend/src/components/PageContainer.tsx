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
 * 提供统一的页面布局：外层 px-6 py-4 内边距 + container 内容区域
 */
const PageContainer = ({ children, title, className = '' }: PageContainerProps) => {
  return (
    <div className={`px-6 py-4 ${className}`}>
      {/* 页面标题区域 */}
      {title && (
        <div className="container mx-auto mb-6">
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
            {title}
          </h1>
        </div>
      )}

      {/* 页面内容区域 */}
      <div className="container mx-auto">
        {children}
      </div>
    </div>
  );
};

export default PageContainer;
