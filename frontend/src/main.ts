import { createApp } from 'vue'
import App from './App.vue'
// @ts-ignore 临时忽略缺少类型声明文件的问题
import router from './router/index.ts'

/**
 * 创建并挂载Vue应用实例
 * 集成路由功能
 */
const app = createApp(App)

// 使用路由
app.use(router)

// 挂载应用
app.mount('#app')