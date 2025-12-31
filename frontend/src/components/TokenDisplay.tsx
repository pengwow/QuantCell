// src/components/TokenDisplay.tsx
import { useState } from "react";
import { TokenIcon } from "@web3icons/react/dynamic";

interface Props {
  symbol: string;
  size?: number;
  style?: React.CSSProperties;
}

export function TokenDisplay({ symbol, size = 32, style }: Props) {
  const [hasError, setHasError] = useState(false);

  // 当TokenIcon加载失败时显示首字母
  if (hasError) {
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