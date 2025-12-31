/**
 * 响应式布局工具组件
 * 功能：提供屏幕尺寸检测和响应式布局工具函数
 */
import { useState, useEffect } from 'react';

// 响应式断点配置
export const breakpoints = {
  xs: 480,
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
  xxl: 1600
} as const;

// 屏幕尺寸类型
export type ScreenSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl';

// 响应式工具hook
export const useResponsive = () => {
  const [screenSize, setScreenSize] = useState<ScreenSize>('lg');

  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth;
      
      if (width < breakpoints.xs) {
        setScreenSize('xs');
      } else if (width < breakpoints.sm) {
        setScreenSize('sm');
      } else if (width < breakpoints.md) {
        setScreenSize('md');
      } else if (width < breakpoints.lg) {
        setScreenSize('lg');
      } else if (width < breakpoints.xl) {
        setScreenSize('xl');
      } else {
        setScreenSize('xxl');
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return {
    screenSize,
    isXs: screenSize === 'xs',
    isSm: screenSize === 'sm',
    isMd: screenSize === 'md',
    isLg: screenSize === 'lg',
    isXl: screenSize === 'xl',
    isXxl: screenSize === 'xxl',
    isMobile: screenSize === 'xs' || screenSize === 'sm',
    isTablet: screenSize === 'md',
    isDesktop: screenSize === 'lg' || screenSize === 'xl' || screenSize === 'xxl'
  };
};

// 媒体查询工具hook
export const useMediaQuery = (query: string) => {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia(query);
    setMatches(mediaQuery.matches);

    const handleChange = (event: MediaQueryListEvent) => {
      setMatches(event.matches);
    };

    mediaQuery.addEventListener('change', handleChange);

    return () => {
      mediaQuery.removeEventListener('change', handleChange);
    };
  }, [query]);

  return matches;
};