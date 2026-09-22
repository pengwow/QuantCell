import React from 'react'
import * as ReactDOMAll from 'react-dom'
import * as ReactDOMClient from 'react-dom/client'
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { isTauri } from './desktop/env'
import { bootstrapDesktop } from './desktop/bootstrap'

// 暴露 React/ReactDOM 全局变量，供插件前端 bundle 动态加载时使用
const win = window as unknown as Record<string, unknown>
win.React = React
win.ReactJSX = { jsx, jsxs, Fragment }
win.ReactDOM = { ...ReactDOMAll, ...ReactDOMClient }

async function main() {
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
