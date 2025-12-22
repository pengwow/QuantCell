<template>
  <div class="app-container">
    <!-- 侧边栏导航 -->
    <aside class="side-nav" :class="{ 'collapsed': isCollapsed }" @mouseenter="isCollapsed = false">
      <!-- 侧边栏顶部品牌 -->
      <div class="nav-brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>
        <div class="brand-text">QBot</div>

      </div>

      <!-- 侧边栏菜单 -->
        <div class="nav-menu" @mouseenter="isCollapsed = false">
        <!-- 策略管理分组 -->
        <div class="menu-group">
          <div class="menu-group-title">策略管理</div>
          <router-link to="/agent/StrategyAgent" class="nav-item">
            <div class="nav-icon">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm-2 14l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/>
              </svg>
            </div>
            <span class="nav-text">策略代理</span>
          </router-link>
          <router-link to="/backtest-results" class="nav-item">
            <div class="nav-icon">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/>
              </svg>
            </div>
            <span class="nav-text">回测结果</span>
          </router-link>
        </div>

        <!-- 因子分析分组 -->
        <div class="menu-group">
          <div class="menu-group-title">因子分析</div>
          <router-link to="/factor-analysis" class="nav-item">
            <div class="nav-icon">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M10.5 1C5.81 1 2 4.81 2 9.5S5.81 18 10.5 18 19 14.19 19 9.5 15.19 1 10.5 1zm0 15c-2.49 0-4.5-2.01-4.5-4.5S8.01 6 10.5 6 15 8.01 15 10.5 12.99 16 10.5 16zm0-11C9.12 5 8 6.12 8 7.5S9.12 10 10.5 10 13 8.88 13 7.5 11.88 5 10.5 5zm0 9C12.99 14 15 11.99 15 9.5S12.99 5 10.5 5 6 7.01 6 9.5 8.01 14 10.5 14z"/>
              </svg>
            </div>
            <span class="nav-text">因子分析</span>
          </router-link>
        </div>

        <!-- 模型管理分组 -->
        <div class="menu-group">
          <div class="menu-group-title">模型管理</div>
          <router-link to="/model-management" class="nav-item">
            <div class="nav-icon">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
              </svg>
            </div>
            <span class="nav-text">模型管理</span>
          </router-link>
        </div>

        <!-- 数据管理分组 -->
        <div class="menu-group">
          <div class="menu-group-title">数据管理</div>
          <router-link to="/data-management" class="nav-item">
            <div class="nav-icon">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/>
              </svg>
            </div>
            <span class="nav-text">数据管理</span>
          </router-link>
          <router-link to="/chart" class="nav-item">
            <div class="nav-icon">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M3 3v18h18V3H3zm16 16H5V5h14v14zm-5.5-4.37L14.59 16 16 14.59 13.41 12 16 9.41 14.59 8 12 10.59 9.41 8 8 9.41 10.59 12 8 14.59 9.41 16 12 13.41z"/>
              </svg>
            </div>
            <span class="nav-text">K线图表</span>
          </router-link>
        </div>
      </div>

      <!-- 设置按钮放在底部 -->
      <div class="nav-bottom" @mouseenter="isCollapsed = false">
        <router-link to="/setting" class="nav-item">
          <div class="nav-icon">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
            </svg>
          </div>
          <span class="nav-text">系统设置</span>
        </router-link>
      </div>
    </aside>

    <!-- 主内容区域 -->
    <main class="main-container" @mouseenter="isCollapsed = true">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- 页脚
    <footer class="main-footer">
      <div class="footer-content">
        <p>&copy; 2025 xxxxx | 版本 v1.0.0</p>
      </div>
    </footer> -->
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue'
import { useRouter } from 'vue-router'

/**
 * 侧边栏导航组件
 * 功能：实现左侧图标菜单布局，支持鼠标悬停显示文字描述，设置按钮位于底部，支持收放功能
 */
export default defineComponent({
  name: 'App',
  setup() {
    // 使用Vue Router
    const router = useRouter()
    
    // 侧边栏收放状态 - 默认收起
    const isCollapsed = ref(true)
    
    /**
     * 处理菜单点击事件
     * @param {string} path - 路由路径
     */
    const handleMenuClick = (path: string): void => {
      router.push(path)
      // 点击菜单后自动切换收放状态
      isCollapsed.value = true
    }
    

    
    return {
      handleMenuClick,
      isCollapsed
    }
  }
})
</script>

<style>
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
  line-height: 1.6;
  color: #333;
  background-color: #f5f7fa;
}

/* 应用容器 - 改为水平布局 */
.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: row;
}

/* 侧边栏样式 */
.side-nav {
  width: 200px;
  background-color: white;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  z-index: 100;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  overflow-y: auto;
  overflow-x: hidden;
}

/* 侧边栏收起状态 */
.side-nav.collapsed {
  width: 60px;
  box-shadow: 1px 0 4px rgba(0, 0, 0, 0.08);
}

/* 侧边栏品牌区域 */
.nav-brand {
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #f0f0f0;
  position: relative;
  transition: padding 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.brand-icon {
  width: 32px;
  height: 32px;
  color: #4a6cf7;
  transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
  /* 固定图标位置，避免展开收起时移动 */
  margin-left: 4px;
}

.brand-icon svg {
  width: 100%;
  height: 100%;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.brand-text {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
  transition: opacity 0.35s cubic-bezier(0.4, 0, 0.2, 1), width 0.35s cubic-bezier(0.4, 0, 0.2, 1), margin 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
  overflow: hidden;
  flex-shrink: 0;
}

/* 侧边栏菜单区域 */
.nav-menu {
  flex: 1;
  padding: 20px 0;
  overflow: visible;
  transition: padding 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 菜单分组 */
.menu-group {
  margin-bottom: 24px;
  transition: margin-bottom 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 菜单分组标题 */
.menu-group-title {
  font-size: 12px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0 20px 8px;
  transition: opacity 0.35s cubic-bezier(0.4, 0, 0.2, 1), padding 0.35s cubic-bezier(0.4, 0, 0.2, 1), width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
  overflow: hidden;
  flex-shrink: 0;
  position: relative;
}

/* 侧边栏底部区域 - 放置设置按钮 */
.nav-bottom {
  padding: 20px 0;
  border-top: 1px solid #f0f0f0;
  margin-top: auto;
  transition: padding 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 菜单项样式 */
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  color: #6b7280;
  text-decoration: none;
  position: relative;
  transition: all 0.25s ease-in-out;
  cursor: pointer;
  border-left: 3px solid transparent;
}

/* 图标样式 */
.nav-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
  /* 固定图标位置，避免展开收起时移动 */
  margin-left: 4px;
}

/* 侧边栏收起时隐藏文字内容 */
.side-nav.collapsed .brand-text,
.side-nav.collapsed .menu-group-title,
.side-nav.collapsed .nav-text {
  opacity: 0;
  width: 0;
  margin: 0;
  overflow: hidden;
  white-space: nowrap;
}

/* 侧边栏收起时调整菜单项样式 */
.side-nav.collapsed .nav-item {
  padding: 12px 10px;
  gap: 0;
}

/* 侧边栏收起时调整品牌区域 */
.side-nav.collapsed .nav-brand {
  padding: 20px 10px;
  gap: 0;
}

/* 图标样式 */
.nav-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
}

.nav-icon svg {
  width: 100%;
  height: 100%;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 文字描述 */
.nav-text {
  font-size: 14px;
  font-weight: 400;
  color: inherit;
  white-space: nowrap;
  transition: opacity 0.35s cubic-bezier(0.4, 0, 0.2, 1), width 0.35s cubic-bezier(0.4, 0, 0.2, 1), margin 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
  overflow: hidden;
}

/* 鼠标悬停效果 */
.nav-item:hover {
  background-color: #f0f4ff;
  color: #4a6cf7;
}

/* 激活状态样式 */
.nav-item.router-link-active {
  background-color: #f0f4ff;
  color: #4a6cf7;
  border-left-color: #4a6cf7;
  font-weight: 500;
}

/* 滚动条样式 */
.side-nav::-webkit-scrollbar {
  width: 6px;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.side-nav::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.side-nav::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.side-nav::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.side-nav.collapsed::-webkit-scrollbar {
  width: 0;
}

/* 主内容区域 - 调整为侧边栏布局 */
.main-container {
  flex: 1;
  margin-left: 200px;
  padding: 24px;
  min-height: 100vh;
  background-color: #f9fafb;
  transition: margin-left 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 页脚样式 */
.main-footer {
  background-color: white;
  border-top: 1px solid #e0e0e0;
  padding: 20px;
  margin-left: 200px;
  transition: margin-left 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 侧边栏收起时调整主内容和页脚 */
.side-nav.collapsed ~ .main-container,
.side-nav.collapsed ~ .main-footer {
  margin-left: 60px;
}

.footer-content {
  text-align: center;
  font-size: 14px;
  color: #666;
}

/* 页面过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .side-nav {
    width: 60px;
  }
  
  .side-nav:not(.collapsed) {
    width: 180px;
  }
  
  .main-container,
  .main-footer {
    margin-left: 60px;
  }
  
  .side-nav:not(.collapsed) ~ .main-container,
  .side-nav:not(.collapsed) ~ .main-footer {
    margin-left: 180px;
  }
  
  .main-container {
    padding: 15px;
  }
  
  .nav-item {
    padding: 12px 8px;
  }
}  
</style>