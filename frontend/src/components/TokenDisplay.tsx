// src/components/TokenDisplay.tsx
import React, { useState, useEffect } from "react";

// 使用动态导入，实现懒加载
let TokenIcon: React.ComponentType<any> | null = null;

interface Props {
  symbol: string;
  size?: number;
  style?: React.CSSProperties;
}

export function TokenDisplay({ symbol, size = 32, style }: Props) {
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // 动态导入 TokenIcon 组件
  useEffect(() => {
    const loadTokenIcon = async () => {
      try {
        setIsLoading(true);
        const { TokenIcon: LoadedTokenIcon } = await import("@web3icons/react/dynamic");
        TokenIcon = LoadedTokenIcon;
        setIsLoading(false);
      } catch (error) {
        console.error("Failed to load TokenIcon:", error);
        setHasError(true);
        setIsLoading(false);
      }
    };

    if (!TokenIcon && !hasError) {
      loadTokenIcon();
    } else {
      setIsLoading(false);
    }
  }, [hasError]);

  // 当TokenIcon加载失败时显示首字母
  if (hasError || !TokenIcon) {
    const initial = symbol.charAt(0).toUpperCase();
    return (
      <div 
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: "50%",
          backgroundColor: "#ffc53d",
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

  // 加载中状态
  if (isLoading) {
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
          ...style
        }}
      />
    );
  }

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