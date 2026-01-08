/**
 * 错误边界组件
 * 用于捕获和处理子组件中的JavaScript错误
 */
import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { Alert } from 'antd';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // 更新状态，以便下一次渲染显示降级UI
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // 可以将错误日志上报到服务器
    console.error('错误边界捕获到错误:', error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      // 自定义降级UI
      return (
        <div style={{ padding: '20px' }}>
          <Alert
            message="组件发生错误"
            description="抱歉，组件发生了错误，我们正在努力修复。"
            type="error"
            showIcon
          />
          <div style={{ marginTop: '20px' }}>
            <h4>错误信息:</h4>
            <pre style={{ backgroundColor: '#f0f0f0', padding: '10px', borderRadius: '4px' }}>
              {this.state.error && this.state.error.toString()}
            </pre>
            {this.state.errorInfo && (
              <>
                <h4>错误堆栈:</h4>
                <pre style={{ backgroundColor: '#f0f0f0', padding: '10px', borderRadius: '4px', maxHeight: '300px', overflow: 'auto' }}>
                  {this.state.errorInfo.componentStack}
                </pre>
              </>
            )}
          </div>
        </div>
      );
    }

    // 正常情况下，渲染子组件
    return this.props.children;
  }
}

export default ErrorBoundary;