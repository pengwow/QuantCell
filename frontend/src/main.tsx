import React from 'react'
import * as ReactDOMAll from 'react-dom'
import * as ReactDOMClient from 'react-dom/client'
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'

// 暴露 React/ReactDOM 全局变量，供插件前端 bundle 动态加载时使用
const win = window as unknown as Record<string, unknown>
win.React = React
win.ReactJSX = { jsx, jsxs, Fragment }
win.ReactDOM = { ...ReactDOMAll, ...ReactDOMClient }

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
