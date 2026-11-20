import React from 'react'
import * as ReactDOMAll from 'react-dom'
import * as ReactDOMClient from 'react-dom/client'
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { isTauri } from './desktop/env'
import { bootstrapDesktop } from './desktop/bootstrap'
import { applyThemeVars } from './theme'

// 暴露 React/ReactDOM 全局变量，供插件前端 bundle 动态加载时使用
const win = window as unknown as Record<string, unknown>
win.React = React
win.ReactJSX = { jsx, jsxs, Fragment }
win.ReactDOM = { ...ReactDOMAll, ...ReactDOMClient }

async function main() {
  // 首帧主题变量：index.html 内联脚本只锁 dark class 与背景兜底，
  // 完整 --qc-* / --tw-color-* 调色板在这里（React 渲染前）从 src/theme 注入
  applyThemeVars(document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  // 桌面壳：先完成 sidecar 引导与网络注入，再渲染业务 bundle；Web 版直接渲染
  if (isTauri()) {
    await bootstrapDesktop()
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void main()
