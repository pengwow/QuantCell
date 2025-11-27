<template>
  <div class="settings-container">
    <header class="page-header">
      <h1>系统设置</h1>
    </header>

    <div class="settings-content">
      <!-- 侧边栏导航 -->
      <aside class="settings-sidebar">
        <nav class="settings-nav">
          <ul>
            <li 
              v-for="menu in menuItems" 
              :key="menu.id"
              :class="{ active: currentTab === menu.id }"
              @click="currentTab = menu.id"
            >
              <i :class="menu.icon"></i>
              <span>{{ menu.title }}</span>
            </li>
          </ul>
        </nav>
      </aside>

      <!-- 主内容区域 -->
      <main class="settings-main">
        <!-- 基本设置 -->
        <div v-if="currentTab === 'basic'" class="settings-panel">
          <h2>基本设置</h2>
          <div class="form-section">
            <h3>个人信息</h3>
            <div class="form-group">
              <label for="username">用户名</label>
              <input 
                id="username" 
                v-model="settings.username" 
                type="text" 
                class="form-control"
                :disabled="true"
              >
            </div>
            <div class="form-group">
              <label for="displayName">显示名称</label>
              <input 
                id="displayName" 
                v-model="settings.displayName" 
                type="text" 
                class="form-control"
                placeholder="请输入显示名称"
              >
            </div>
            <div class="form-group">
              <label for="email">邮箱</label>
              <input 
                id="email" 
                v-model="settings.email" 
                type="email" 
                class="form-control"
                placeholder="请输入邮箱地址"
              >
            </div>
          </div>

          <div class="form-section">
            <h3>界面设置</h3>
            <div class="form-group">
              <label for="theme">主题</label>
              <select id="theme" v-model="settings.theme" class="form-control">
                <option value="light">浅色</option>
                <option value="dark">深色</option>
                <option value="auto">跟随系统</option>
              </select>
            </div>
            <div class="form-group">
              <label for="language">语言</label>
              <select id="language" v-model="settings.language" class="form-control">
                <option value="zh-CN">简体中文</option>
                <option value="en-US">English (US)</option>
              </select>
            </div>
            <div class="form-group checkbox-group">
              <input 
                id="showTips" 
                v-model="settings.showTips" 
                type="checkbox" 
              >
              <label for="showTips">显示功能提示</label>
            </div>
          </div>
        </div>

        <!-- 通知设置 -->
        <div v-if="currentTab === 'notifications'" class="settings-panel">
          <h2>通知设置</h2>
          <div class="form-section">
            <h3>通知方式</h3>
            <div class="form-group checkbox-group">
              <input 
                id="enableEmail" 
                v-model="notificationSettings.enableEmail" 
                type="checkbox" 
              >
              <label for="enableEmail">邮件通知</label>
            </div>
            <div class="form-group checkbox-group">
              <input 
                id="enableWebhook" 
                v-model="notificationSettings.enableWebhook" 
                type="checkbox" 
              >
              <label for="enableWebhook">Webhook 通知</label>
            </div>
            <div v-if="notificationSettings.enableWebhook" class="form-group">
              <label for="webhookUrl">Webhook URL</label>
              <input 
                id="webhookUrl" 
                v-model="notificationSettings.webhookUrl" 
                type="text" 
                class="form-control"
                placeholder="请输入 Webhook URL"
              >
            </div>
          </div>

          <div class="form-section">
            <h3>通知内容</h3>
            <div class="form-group checkbox-group">
              <input 
                id="notifyOnAlert" 
                v-model="notificationSettings.notifyOnAlert" 
                type="checkbox" 
              >
              <label for="notifyOnAlert">告警通知</label>
            </div>
            <div class="form-group checkbox-group">
              <input 
                id="notifyOnTaskComplete" 
                v-model="notificationSettings.notifyOnTaskComplete" 
                type="checkbox" 
              >
              <label for="notifyOnTaskComplete">任务完成通知</label>
            </div>
            <div class="form-group checkbox-group">
              <input 
                id="notifyOnSystemUpdate" 
                v-model="notificationSettings.notifyOnSystemUpdate" 
                type="checkbox" 
              >
              <label for="notifyOnSystemUpdate">系统更新通知</label>
            </div>
          </div>
        </div>

        <!-- API 配置 -->
        <div v-if="currentTab === 'api'" class="settings-panel">
          <h2>API 配置</h2>
          <div class="form-section">
            <h3>API 密钥</h3>
            <div class="form-group">
              <label>API Key</label>
              <div class="input-group">
                <input 
                  v-model="apiSettings.apiKey" 
                  type="text" 
                  class="form-control"
                  :disabled="true"
                >
                <button class="btn btn-secondary" @click="regenerateApiKey">
                  重新生成
                </button>
              </div>
              <p class="help-text">
                API Key 用于调用系统 API。请妥善保管，避免泄露。
              </p>
            </div>
          </div>

          <div class="form-section">
            <h3>API 权限</h3>
            <div class="permission-list">
              <div v-for="permission in apiSettings.permissions" :key="permission.id" class="permission-item">
                <div class="permission-info">
                  <h4>{{ permission.name }}</h4>
                  <p>{{ permission.description }}</p>
                </div>
                <div class="permission-toggle">
                  <label class="switch">
                    <input 
                      v-model="permission.enabled" 
                      type="checkbox" 
                    >
                    <span class="slider round"></span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 系统信息 -->
        <div v-if="currentTab === 'system'" class="settings-panel">
          <h2>系统信息</h2>
          <div class="system-info">
            <div class="info-section">
              <h3>版本信息</h3>
              <div class="info-item">
                <span class="info-label">系统版本：</span>
                <span class="info-value">{{ systemInfo.version }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">构建日期：</span>
                <span class="info-value">{{ systemInfo.buildDate }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">API 版本：</span>
                <span class="info-value">{{ systemInfo.apiVersion }}</span>
              </div>
            </div>

            <div class="info-section">
              <h3>运行状态</h3>
              <div class="info-item">
                <span class="info-label">运行时间：</span>
                <span class="info-value">{{ systemInfo.uptime }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">服务状态：</span>
                <span class="info-value status-running">{{ systemInfo.status }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">最后检查：</span>
                <span class="info-value">{{ systemInfo.lastCheck }}</span>
              </div>
            </div>

            <div class="info-section">
              <h3>资源使用</h3>
              <div class="info-item">
                <span class="info-label">CPU 使用率：</span>
                <span class="info-value">{{ systemInfo.cpuUsage }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">内存使用：</span>
                <span class="info-value">{{ systemInfo.memoryUsage }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">磁盘空间：</span>
                <span class="info-value">{{ systemInfo.diskSpace }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部操作按钮 -->
        <div class="settings-footer" v-if="currentTab !== 'system'">
          <button class="btn btn-secondary" @click="resetSettings">
            重置
          </button>
          <button class="btn btn-primary" @click="saveSettings">
            保存设置
          </button>
        </div>
      </main>
    </div>

    <!-- 保存成功提示 -->
    <div v-if="showSuccessMessage" class="success-message">
      设置已成功保存！
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, reactive, ref, onMounted } from 'vue'

/**
 * 菜单项类型定义
 */
interface MenuItem {
  id: string
  title: string
  icon: string
}

/**
 * 用户设置类型定义
 */
interface UserSettings {
  username: string
  displayName: string
  email: string
  theme: 'light' | 'dark' | 'auto'
  language: 'zh-CN' | 'en-US'
  showTips: boolean
}

/**
 * 通知设置类型定义
 */
interface NotificationSettings {
  enableEmail: boolean
  enableWebhook: boolean
  webhookUrl: string
  notifyOnAlert: boolean
  notifyOnTaskComplete: boolean
  notifyOnSystemUpdate: boolean
}

/**
 * API权限类型定义
 */
interface ApiPermission {
  id: string
  name: string
  description: string
  enabled: boolean
}

/**
 * API设置类型定义
 */
interface ApiSettings {
  apiKey: string
  permissions: ApiPermission[]
}

/**
 * 系统信息类型定义
 */
interface SystemInfo {
  version: string
  buildDate: string
  apiVersion: string
  uptime: string
  status: string
  lastCheck: string
  cpuUsage: string
  memoryUsage: string
  diskSpace: string
}

/**
 * 原始设置类型定义
 */
interface OriginalSettings {
  basic: UserSettings
  notifications: NotificationSettings
  api: ApiSettings
}

/**
 * 设置页面组件
 * 功能：提供用户界面配置、通知设置、API配置、系统信息等功能
 */
export default defineComponent({
  name: 'Setting',
  setup() {
    // 当前选中的标签页
    const currentTab = ref<string>('basic')
    
    // 显示成功消息标志
    const showSuccessMessage = ref<boolean>(false)
    
    // 菜单项列表
    const menuItems: MenuItem[] = [
      { id: 'basic', title: '基本设置', icon: 'icon-basic' },
      { id: 'notifications', title: '通知设置', icon: 'icon-notification' },
      { id: 'api', title: 'API 配置', icon: 'icon-api' },
      { id: 'system', title: '系统信息', icon: 'icon-system' }
    ]
    
    // 用户设置
    const settings = reactive<UserSettings>({
      username: 'admin',
      displayName: '系统管理员',
      email: 'admin@example.com',
      theme: 'light',
      language: 'zh-CN',
      showTips: true
    })
    
    // 通知设置
    const notificationSettings = reactive<NotificationSettings>({
      enableEmail: true,
      enableWebhook: false,
      webhookUrl: '',
      notifyOnAlert: true,
      notifyOnTaskComplete: true,
      notifyOnSystemUpdate: false
    })
    
    // API设置
    const apiSettings = reactive<ApiSettings>({
      apiKey: 'sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
      permissions: [
        {
          id: 'read',
          name: '读取权限',
          description: '允许读取系统数据和配置',
          enabled: true
        },
        {
          id: 'write',
          name: '写入权限',
          description: '允许修改系统数据和配置',
          enabled: false
        },
        {
          id: 'execute',
          name: '执行权限',
          description: '允许执行系统操作和任务',
          enabled: true
        }
      ]
    })
    
    // 系统信息
    const systemInfo = reactive<SystemInfo>({
      version: 'v1.2.3',
      buildDate: '2024-01-20',
      apiVersion: 'v2',
      uptime: '5 天 12 小时',
      status: '正常运行',
      lastCheck: '2024-01-20 15:30:00',
      cpuUsage: '12.5%',
      memoryUsage: '3.2 GB / 8.0 GB',
      diskSpace: '128 GB / 500 GB'
    })
    
    // 原始设置
    const originalSettings = ref<OriginalSettings>({} as OriginalSettings)
    
    /**
     * 保存设置
     * @returns {Promise<void>}
     */
    const saveSettings = async (): Promise<void> => {
      console.log('保存设置:', {
        basic: settings,
        notifications: notificationSettings,
        api: apiSettings
      })
      
      // 模拟保存操作
      setTimeout(() => {
        showSuccessMessage.value = true
        // 3秒后隐藏成功提示
        setTimeout(() => {
          showSuccessMessage.value = false
        }, 3000)
      }, 500)
    }
    
    /**
     * 重置设置
     */
    const resetSettings = (): void => {
      if (confirm('确定要重置当前设置吗？')) {
        Object.assign(settings, { ...originalSettings.value.basic })
        Object.assign(notificationSettings, { ...originalSettings.value.notifications })
        Object.assign(apiSettings, { ...originalSettings.value.api })
      }
    }
    
    /**
     * 重新生成 API Key
     */
    const regenerateApiKey = (): void => {
      if (confirm('确定要重新生成 API Key 吗？当前的 API Key 将失效。')) {
        // 模拟生成随机 API Key
        const randomKey = 'sk_' + Math.random().toString(36).substring(2, 34)
        apiSettings.apiKey = randomKey
        console.log('新的 API Key:', randomKey)
      }
    }
    
    /**
     * 组件挂载时保存原始设置
     */
    onMounted(() => {
      // 保存原始设置，用于重置功能
      originalSettings.value = {
        basic: { ...settings },
        notifications: { ...notificationSettings },
        api: { ...apiSettings }
      }
    })
    
    return {
      currentTab,
      showSuccessMessage,
      menuItems,
      settings,
      notificationSettings,
      apiSettings,
      systemInfo,
      originalSettings,
      saveSettings,
      resetSettings,
      regenerateApiKey
    }
  }
})
</script>

<style scoped>
.settings-container {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 30px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.page-header h1 {
  margin: 0;
  font-size: 28px;
  color: #333;
}

.settings-content {
  display: flex;
  gap: 30px;
  min-height: 600px;
}

.settings-sidebar {
  width: 240px;
  flex-shrink: 0;
}

.settings-nav ul {
  list-style: none;
  padding: 0;
  margin: 0;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border: 1px solid #e0e0e0;
}

.settings-nav li {
  display: flex;
  align-items: center;
  padding: 15px 20px;
  cursor: pointer;
  transition: background-color 0.3s;
  color: #666;
  font-size: 14px;
}

.settings-nav li:hover {
  background-color: #f8f9fa;
}

.settings-nav li.active {
  background-color: #4a6cf7;
  color: white;
  font-weight: 500;
}

.settings-nav li i {
  margin-right: 12px;
  font-size: 16px;
}

/* 模拟图标 */
.icon-basic::before { content: '⚙️'; }
.icon-notification::before { content: '🔔'; }
.icon-api::before { content: '🔑'; }
.icon-system::before { content: '🖥️'; }

.settings-main {
  flex: 1;
  background: white;
  border-radius: 8px;
  padding: 30px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border: 1px solid #e0e0e0;
}

.settings-panel h2 {
  margin-top: 0;
  margin-bottom: 30px;
  font-size: 24px;
  color: #333;
}

.form-section {
  margin-bottom: 40px;
}

.form-section h3 {
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 18px;
  color: #555;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #333;
  font-size: 14px;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.3s;
}

.form-control:focus {
  outline: none;
  border-color: #4a6cf7;
  box-shadow: 0 0 0 2px rgba(74, 108, 247, 0.1);
}

.form-control:disabled {
  background-color: #f8f9fa;
  color: #6c757d;
}

.checkbox-group {
  display: flex;
  align-items: center;
}

.checkbox-group input[type="checkbox"] {
  margin-right: 10px;
  width: auto;
}

.checkbox-group label {
  margin-bottom: 0;
  font-weight: normal;
}

.input-group {
  display: flex;
  gap: 10px;
}

.input-group .form-control {
  flex: 1;
}

.help-text {
  margin-top: 8px;
  font-size: 12px;
  color: #6c757d;
  margin-bottom: 0;
}

.permission-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.permission-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  background-color: #f8f9fa;
  border-radius: 6px;
}

.permission-info h4 {
  margin: 0 0 5px 0;
  font-size: 16px;
  color: #333;
}

.permission-info p {
  margin: 0;
  font-size: 14px;
  color: #666;
}

/* 开关样式 */
.switch {
  position: relative;
  display: inline-block;
  width: 50px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: .4s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .4s;
}

input:checked + .slider {
  background-color: #4a6cf7;
}

input:focus + .slider {
  box-shadow: 0 0 1px #4a6cf7;
}

input:checked + .slider:before {
  transform: translateX(26px);
}

.slider.round {
  border-radius: 24px;
}

.slider.round:before {
  border-radius: 50%;
}

/* 系统信息样式 */
.system-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 30px;
}

.info-section {
  background-color: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
}

.info-section h3 {
  margin-top: 0;
  margin-bottom: 15px;
  font-size: 18px;
  color: #333;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #e9ecef;
}

.info-item:last-child {
  border-bottom: none;
}

.info-label {
  font-size: 14px;
  color: #666;
}

.info-value {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.status-running {
  color: #2ed573;
}

/* 底部按钮 */
.settings-footer {
  display: flex;
  justify-content: flex-end;
  gap: 15px;
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid #f0f0f0;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.3s;
}

.btn-primary {
  background-color: #4a6cf7;
  color: white;
}

.btn-primary:hover {
  background-color: #3a5ad9;
}

.btn-secondary {
  background-color: #e0e0e0;
  color: #333;
}

.btn-secondary:hover {
  background-color: #d0d0d0;
}

/* 成功提示 */
.success-message {
  position: fixed;
  top: 20px;
  right: 20px;
  background-color: #2ed573;
  color: white;
  padding: 15px 25px;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .settings-content {
    flex-direction: column;
  }
  
  .settings-sidebar {
    width: 100%;
  }
  
  .settings-nav ul {
    display: flex;
    overflow-x: auto;
    border-radius: 8px;
  }
  
  .settings-nav li {
    white-space: nowrap;
    min-width: 120px;
    justify-content: center;
  }
  
  .system-info {
    grid-template-columns: 1fr;
  }
  
  .input-group {
    flex-direction: column;
  }
  
  .permission-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}
</style>