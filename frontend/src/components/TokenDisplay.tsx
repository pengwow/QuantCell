// src/components/TokenDisplay.tsx
import React, { useState, useEffect } from "react";

// 使用Vite环境变量检测是否为Tauri打包环境
// VITE_IS_TAURI=1 或 VITE_IS_TAURI=true 表示Tauri环境
const isTauri = import.meta.env.VITE_IS_TAURI === '1' || import.meta.env.VITE_IS_TAURI === 'true';

// 定义更宽松的TokenIcon组件类型，兼容实际导入的组件类型
// 使用any类型来避免类型不匹配问题，因为我们无法在编译时知道实际的类型
let TokenIcon: React.ComponentType<any> | null = null;

interface Props {
  symbol: string;
  size?: number;
  style?: React.CSSProperties;
}

export function TokenDisplay({ symbol, size = 32, style }: Props) {
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // 动态导入 TokenIcon 组件 - 仅在Tauri环境下尝试加载
  useEffect(() => {
    // 非Tauri环境下，直接使用默认图标，不尝试加载web3icons
    if (!isTauri) {
      setIsLoading(false);
      return;
    }

    const loadTokenIcon = async () => {
      try {
        setIsLoading(true);
        // 动态导入web3icons包
        const { TokenIcon: LoadedTokenIcon } = await import("@web3icons/react/dynamic");
        TokenIcon = LoadedTokenIcon;
        setIsLoading(false);
      } catch (error) {
        console.error("Failed to load TokenIcon:", error);
        setHasError(true);
        setIsLoading(false);
      }
    };

    // 只有在Tauri环境下且TokenIcon未加载且无错误时才尝试加载
    if (isTauri && !TokenIcon && !hasError) {
      loadTokenIcon();
    } else {
      setIsLoading(false);
    }
  }, [hasError]);

  // 生成默认图标颜色 - 根据symbol生成哈希值，映射到固定颜色
  const getDefaultIconColor = (symbol: string): string => {
    // 简单的哈希函数，将symbol转换为颜色
    let hash = 0;
    for (let i = 0; i < symbol.length; i++) {
      hash = symbol.charCodeAt(i) + ((hash << 5) - hash);
    }
    
    // 生成HSL颜色，确保亮度和饱和度适中
    const hue = hash % 360;
    return `hsl(${hue}, 70%, 60%)`;
  };

  // 当TokenIcon加载失败、未加载或非Tauri环境时显示默认图标
  if (hasError || !TokenIcon || !isTauri) {
    const initial = symbol.charAt(0).toUpperCase();
    const bgColor = getDefaultIconColor(symbol);
    
    return (
      <div 
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: "50%",
          backgroundColor: bgColor,
          color: "white",
          fontSize: `${size * 0.6}px`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: "bold",
          ...style
        }}
      >
        {initial}
      </div>
    );
  }

  // 加载中状态 - 仅在Tauri环境下显示
  if (isLoading && isTauri) {
    const initial = symbol.charAt(0).toUpperCase();
    return (
      <div 
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: "50%",
          backgroundColor: "#f0f0f0",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: "bold",
          fontSize: `${size * 0.6}px`,
          color: "#999",
          ...style
        }}
      >
        {initial}
      </div>
    );
  }

  // Tauri环境下正常使用TokenIcon组件
  return (
    <TokenIcon 
      symbol={symbol} 
      size={size} 
      variant="branded" 
      style={style}
      onError={() => setHasError(true)} 
    />
  );
}

// 默认导出 TokenDisplay 组件
export default TokenDisplay;
