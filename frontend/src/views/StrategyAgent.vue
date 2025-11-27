<template>
  <div class="strategy-agent-container">
    <header class="page-header">
      <h1>策略代理</h1>
      <div class="header-actions">
        <button class="btn btn-primary" @click="createNewStrategy">新建策略</button>
        <button class="btn btn-secondary" @click="refreshData">刷新</button>
      </div>
    </header>

    <main class="main-content">
      <!-- 策略列表 -->
      <div class="strategy-list">
        <h2>已配置的策略</h2>
        <div class="strategy-cards">
          <div 
            v-for="strategy in strategies" 
            :key="strategy.id" 
            class="strategy-card"
            @click="viewStrategyDetail(strategy.id)"
          >
            <div class="card-header">
              <h3>{{ strategy.name }}</h3>
              <span class="status-badge" :class="`status-${strategy.status}`">
                {{ strategy.statusText }}
              </span>
            </div>
            <div class="card-body">
              <p class="description">{{ strategy.description }}</p>
              <div class="strategy-meta">
                <span class="meta-item">
                  <i class="icon-calendar"></i>
                  {{ strategy.createdAt }}
                </span>
                <span class="meta-item">
                  <i class="icon-author"></i>
                  {{ strategy.createdBy }}
                </span>
              </div>
            </div>
            <div class="card-footer">
              <button class="btn btn-sm btn-primary" @click.stop="editStrategy(strategy.id)">
                编辑
              </button>
              <button 
                class="btn btn-sm" 
                :class="strategy.status === 'active' ? 'btn-danger' : 'btn-success'"
                @click.stop="toggleStrategyStatus(strategy.id)"
              >
                {{ strategy.status === 'active' ? '禁用' : '启用' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 策略执行统计 -->
      <div class="execution-stats">
        <h2>执行统计</h2>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-number">{{ totalExecutions }}</div>
            <div class="stat-label">总执行次数</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ successfulExecutions }}</div>
            <div class="stat-label">成功执行</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ failedExecutions }}</div>
            <div class="stat-label">失败执行</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ activeStrategies }}</div>
            <div class="stat-label">活跃策略数</div>
          </div>
        </div>
      </div>
    </main>

    <!-- 策略详情模态框 -->
    <div v-if="showDetailModal" class="modal-overlay" @click="closeDetailModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>策略详情</h3>
          <button class="close-btn" @click="closeDetailModal">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="selectedStrategy" class="strategy-detail">
            <h4>{{ selectedStrategy.name }}</h4>
            <p class="detail-description">{{ selectedStrategy.description }}</p>
            <div class="detail-info">
              <p><strong>状态：</strong><span :class="`status-${selectedStrategy.status}`">{{ selectedStrategy.statusText }}</span></p>
              <p><strong>创建时间：</strong>{{ selectedStrategy.createdAt }}</p>
              <p><strong>创建人：</strong>{{ selectedStrategy.createdBy }}</p>
              <p><strong>最近更新：</strong>{{ selectedStrategy.updatedAt }}</p>
              <p><strong>执行频率：</strong>{{ selectedStrategy.executionFrequency }}</p>
              <p><strong>规则数量：</strong>{{ selectedStrategy.ruleCount }}</p>
            </div>
            <div class="execution-history">
              <h5>最近执行记录</h5>
              <ul v-if="selectedStrategy.executionHistory.length > 0">
                <li v-for="(record, index) in selectedStrategy.executionHistory" :key="index">
                  {{ record.timestamp }} - {{ record.status === 'success' ? '成功' : '失败' }}
                </li>
              </ul>
              <p v-else>暂无执行记录</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, reactive, ref, onMounted } from 'vue'

/**
 * 策略执行历史记录类型
 */
interface ExecutionHistory {
  timestamp: string
  status: 'success' | 'failed'
}

/**
 * 策略类型定义
 */
interface Strategy {
  id: string
  name: string
  description: string
  status: 'active' | 'inactive'
  statusText: string
  createdAt: string
  updatedAt: string
  createdBy: string
  executionFrequency: string
  ruleCount: number
  executionHistory: ExecutionHistory[]
}

export default defineComponent({
  name: 'StrategyAgent',
  setup() {
    // 策略列表数据
    const strategies = reactive<Strategy[]>([])
    
    // 详情模态框显示状态
    const showDetailModal = ref<boolean>(false)
    
    // 选中的策略
    const selectedStrategy = ref<Strategy | null>(null)
    
    // 统计数据
    const totalExecutions = ref<number>(0)
    const successfulExecutions = ref<number>(0)
    const failedExecutions = ref<number>(0)
    const activeStrategies = ref<number>(0)
    
    /**
     * 加载策略列表
     * @returns {Promise<void>}
     */
    const loadStrategies = async (): Promise<void> => {
      // 模拟API调用获取策略数据
      // 在实际应用中，这里应该调用真实的后端API
      strategies.length = 0
      const newStrategies: Strategy[] = [
        {
          id: '1',
          name: '高优先级告警处理',
          description: '自动处理高优先级告警，执行预设的应急响应流程',
          status: 'active',
          statusText: '活跃',
          createdAt: '2024-01-15 10:30:00',
          updatedAt: '2024-01-20 14:20:00',
          createdBy: '系统管理员',
          executionFrequency: '实时',
          ruleCount: 12,
          executionHistory: [
            { timestamp: '2024-01-20 15:30:00', status: 'success' },
            { timestamp: '2024-01-20 14:15:00', status: 'success' },
            { timestamp: '2024-01-20 10:45:00', status: 'failed' }
          ]
        },
        {
          id: '2',
          name: '资源使用率监控',
          description: '监控服务器CPU、内存、磁盘使用率，超过阈值时发出告警',
          status: 'active',
          statusText: '活跃',
          createdAt: '2024-01-10 09:15:00',
          updatedAt: '2024-01-18 11:40:00',
          createdBy: '运维工程师',
          executionFrequency: '5分钟',
          ruleCount: 8,
          executionHistory: [
            { timestamp: '2024-01-20 15:00:00', status: 'success' },
            { timestamp: '2024-01-20 14:55:00', status: 'success' },
            { timestamp: '2024-01-20 14:50:00', status: 'success' }
          ]
        },
        {
          id: '3',
          name: '异常登录检测',
          description: '检测异常登录行为，包括非常规时间、非常规地点登录',
          status: 'inactive',
          statusText: '停用',
          createdAt: '2024-01-05 16:20:00',
          updatedAt: '2024-01-12 13:10:00',
          createdBy: '安全管理员',
          executionFrequency: '实时',
          ruleCount: 15,
          executionHistory: [
            { timestamp: '2024-01-15 09:30:00', status: 'success' },
            { timestamp: '2024-01-14 18:20:00', status: 'success' }
          ]
        }
      ]
      
      newStrategies.forEach(strategy => strategies.push(strategy))
    }

    /**
     * 加载执行统计数据
     * @returns {Promise<void>}
     */
    const loadExecutionStats = async (): Promise<void> => {
      // 模拟API调用获取统计数据
      totalExecutions.value = 456
      successfulExecutions.value = 428
      failedExecutions.value = 28
      activeStrategies.value = 2
    }

    /**
     * 查看策略详情
     * @param {string} strategyId - 策略ID
     */
    const viewStrategyDetail = (strategyId: string): void => {
      selectedStrategy.value = strategies.find(s => s.id === strategyId) || null
      showDetailModal.value = true
    }

    /**
     * 关闭详情模态框
     */
    const closeDetailModal = (): void => {
      showDetailModal.value = false
      selectedStrategy.value = null
    }

    /**
     * 编辑策略
     * @param {string} strategyId - 策略ID
     */
    const editStrategy = (strategyId: string): void => {
      console.log('编辑策略:', strategyId)
      // 在实际应用中，这里应该跳转到编辑页面或打开编辑模态框
      alert(`编辑策略 ${strategyId}`)
    }

    /**
     * 切换策略状态
     * @param {string} strategyId - 策略ID
     */
    const toggleStrategyStatus = (strategyId: string): void => {
      const strategy = strategies.find(s => s.id === strategyId)
      if (strategy) {
        const newStatus = strategy.status === 'active' ? 'inactive' : 'active'
        const newStatusText = strategy.status === 'active' ? '停用' : '活跃'
        
        console.log(`切换策略 ${strategyId} 状态为: ${newStatus}`)
        
        // 更新本地数据
        strategy.status = newStatus
        strategy.statusText = newStatusText
        
        // 更新统计数据
        updateStats()
      }
    }

    /**
     * 创建新策略
     */
    const createNewStrategy = (): void => {
      console.log('创建新策略')
      alert('创建新策略功能')
    }

    /**
     * 刷新数据
     */
    const refreshData = (): void => {
      console.log('刷新数据')
      loadStrategies()
      loadExecutionStats()
    }

    /**
     * 更新统计数据
     */
    const updateStats = (): void => {
      activeStrategies.value = strategies.filter(s => s.status === 'active').length
    }
    
    // 组件挂载时加载数据
    onMounted(() => {
      loadStrategies()
      loadExecutionStats()
    })
    
    return {
      strategies,
      showDetailModal,
      selectedStrategy,
      totalExecutions,
      successfulExecutions,
      failedExecutions,
      activeStrategies,
      createNewStrategy,
      refreshData,
      viewStrategyDetail,
      closeDetailModal,
      editStrategy,
      toggleStrategyStatus,
      updateStats
    }
  }
})
</script>

<style scoped>
.strategy-agent-container {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.page-header h1 {
  margin: 0;
  font-size: 28px;
  color: #333;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
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

.btn-danger {
  background-color: #ff4757;
  color: white;
}

.btn-danger:hover {
  background-color: #ff3838;
}

.btn-success {
  background-color: #2ed573;
  color: white;
}

.btn-success:hover {
  background-color: #26de81;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}

.main-content {
  display: flex;
  gap: 30px;
  flex-wrap: wrap;
}

.strategy-list,
.execution-stats {
  flex: 1;
  min-width: 300px;
}

.strategy-list h2,
.execution-stats h2 {
  margin-bottom: 20px;
  font-size: 20px;
  color: #333;
}

.strategy-cards {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.strategy-card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  border: 1px solid #e0e0e0;
}

.strategy-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-active {
  background-color: #d4edda;
  color: #155724;
}

.status-inactive {
  background-color: #f8f9fa;
  color: #6c757d;
}

.card-body .description {
  margin: 0 0 15px 0;
  color: #666;
  font-size: 14px;
  line-height: 1.5;
}

.strategy-meta {
  display: flex;
  gap: 20px;
  font-size: 12px;
  color: #999;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.card-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #f0f0f0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
}

.stat-card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border: 1px solid #e0e0e0;
}

.stat-number {
  font-size: 32px;
  font-weight: bold;
  color: #4a6cf7;
  margin-bottom: 5px;
}

.stat-label {
  font-size: 14px;
  color: #666;
}

/* 模态框样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 20px;
}

.strategy-detail h4 {
  margin-top: 0;
  margin-bottom: 10px;
  font-size: 22px;
  color: #333;
}

.detail-description {
  margin-bottom: 20px;
  color: #666;
  line-height: 1.6;
}

.detail-info p {
  margin: 8px 0;
  color: #333;
}

.detail-info strong {
  color: #555;
}

.execution-history {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
}

.execution-history h5 {
  margin-top: 0;
  margin-bottom: 10px;
  font-size: 16px;
  color: #333;
}

.execution-history ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.execution-history li {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
  color: #666;
  font-size: 14px;
}

.execution-history li:last-child {
  border-bottom: none;
}
</style>