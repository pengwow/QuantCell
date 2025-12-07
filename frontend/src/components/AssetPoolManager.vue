<template>
  <div class="asset-pool-manager">
    <!-- 顶部操作栏 -->
    <div class="asset-pool-header">
      <div class="header-actions">
        <el-button 
          type="primary"
          size="small"
          @click="showCreatePoolDialog = true"
        >
          <i class="el-icon-plus"></i> 创建资产池
        </el-button>
      </div>
    </div>

    <!-- 搜索框和排序 -->
    <div class="search-sort-container">
      <el-input
        v-model="searchQuery"
        placeholder="搜索资产池名称..."
        clearable
        size="small"
        @input="handleSearch"
        style="width: 300px; margin-right: 10px;"
        autocomplete="off"
        spellcheck="false"
      >
        <template #prefix>
          <i class="el-icon-search"></i>
        </template>
      </el-input>
      <div class="sort-selector">
        <span class="sort-label">排序方式：</span>
        <el-select 
          v-model="sortBy" 
          placeholder="排序" 
          size="small"
          @change="handleSort"
          style="width: 120px; margin-right: 5px;"
        >
          <el-option label="创建时间" value="created_at"></el-option>
          <el-option label="名称" value="name"></el-option>
          <el-option label="资产数量" value="asset_count"></el-option>
        </el-select>
        <el-button 
          type="text" 
          size="small"
          @click="sortDirection = sortDirection === 'asc' ? 'desc' : 'asc'"
        >
          <i :class="sortDirection === 'asc' ? 'el-icon-caret-top' : 'el-icon-caret-bottom'"></i>
        </el-button>
      </div>
    </div>

    <!-- 资产池卡片列表 -->
    <div class="asset-pool-list">
      <h3>已配置的资产池</h3>
      <div class="asset-pool-cards">
        <asset-pool-card
          v-for="pool in filteredPools"
          :key="pool.id"
          :pool="pool"
          @edit="handleEditPool"
          @delete="handleDeletePool"
          @expand="handleExpandPool"
          @update="fetchAssetPools"
        ></asset-pool-card>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="filteredPools.length === 0" class="empty-state">
      <i class="el-icon-document"></i>
      <p>{{ isLoading ? '加载中...' : '暂无资产池数据' }}</p>
      <el-button 
        type="primary"
        @click="showCreatePoolDialog = true"
      >
        <i class="el-icon-plus"></i> 创建第一个资产池
      </el-button>
    </div>

    <!-- 创建/编辑资产池对话框 -->
    <el-dialog
      v-model="showCreatePoolDialog"
      :title="isEditing ? '编辑资产池' : '创建资产池'"
      width="600px"
      center
    >
      <asset-pool-form
        :pool="editingPool"
        :is-editing="isEditing"
        @submit="handleSubmitPool"
        @cancel="handleCancelPool"
      ></asset-pool-form>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
/* @ts-ignore */
import AssetPoolCard from './AssetPoolCard.vue'
/* @ts-ignore */
import AssetPoolForm from './AssetPoolForm.vue'

// 资产池类型定义
interface AssetPool {
  id: number
  name: string
  type: string
  description: string
  color: string
  tags: string
  asset_count: number
  assets?: string[]
  created_at: string
  updated_at: string
}

// 响应式数据
const assetPools = ref<AssetPool[]>([])
const isLoading = ref(false)
const searchQuery = ref('')
const sortBy = ref('created_at')
const sortDirection = ref('desc')
const showCreatePoolDialog = ref(false)
const isEditing = ref(false)
const editingPool = ref<Partial<AssetPool>>({
  name: '',
  type: 'crypto',
  description: '',
  color: '#409EFF',
  tags: '[]'
})

// 计算属性：过滤和排序后的资产池列表
const filteredPools = computed(() => {
  let result = [...assetPools.value]

  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(pool => 
      pool.name.toLowerCase().includes(query) ||
      pool.description.toLowerCase().includes(query)
    )
  }

  // 排序
  result.sort((a, b) => {
    let aValue: any = a[sortBy.value as keyof AssetPool]
    let bValue: any = b[sortBy.value as keyof AssetPool]

    // 处理日期类型
    if (sortBy.value === 'created_at' || sortBy.value === 'updated_at') {
      aValue = new Date(aValue).getTime()
      bValue = new Date(bValue).getTime()
    }

    if (aValue < bValue) {
      return sortDirection.value === 'asc' ? -1 : 1
    }
    if (aValue > bValue) {
      return sortDirection.value === 'asc' ? 1 : -1
    }
    return 0
  })

  return result
})

// 获取资产池列表
const fetchAssetPools = async () => {
  try {
    isLoading.value = true
    const response = await axios.get('/api/data-pools/')
    if (response.data.code === 0) {
      // 将对象转换为数组
      assetPools.value = Object.values(response.data.data) as AssetPool[]
    } else {
      ElMessage.error(`获取资产池失败: ${response.data.message}`)
    }
  } catch (error: any) {
    ElMessage.error(`获取资产池失败: ${error.message}`)
  } finally {
    isLoading.value = false
  }
}

// 处理排序
const handleSort = () => {
  // 排序由computed属性自动处理
}

// 处理搜索
const handleSearch = () => {
  // 搜索由computed属性自动处理
}

// 显示创建资产池对话框已通过模板直接调用，无需单独函数

// 显示编辑资产池对话框
const handleEditPool = (pool: AssetPool) => {
  isEditing.value = true
  editingPool.value = { ...pool }
  showCreatePoolDialog.value = true
}

// 处理删除资产池
const handleDeletePool = async (poolId: number) => {
  try {
    await axios.delete(`/api/data-pools/${poolId}`)
    ElMessage.success('资产池删除成功')
    fetchAssetPools()
  } catch (error: any) {
    ElMessage.error(`删除资产池失败: ${error.message}`)
  }
}

// 处理展开资产池
const handleExpandPool = () => {
  // 由AssetPoolCard组件内部处理
}

// 处理提交资产池
const handleSubmitPool = async (poolData: Partial<AssetPool>) => {
  try {
    if (isEditing.value) {
      // 更新资产池
      await axios.put(`/api/data-pools/${editingPool.value.id}`, poolData)
      ElMessage.success('资产池更新成功')
    } else {
      // 创建资产池
      await axios.post('/api/data-pools/', poolData)
      ElMessage.success('资产池创建成功')
    }
    showCreatePoolDialog.value = false
    fetchAssetPools()
  } catch (error: any) {
    ElMessage.error(`${isEditing.value ? '更新' : '创建'}资产池失败: ${error.message}`)
  }
}

// 处理取消操作
const handleCancelPool = () => {
  showCreatePoolDialog.value = false
}

// 组件挂载时获取资产池列表
onMounted(() => {
  fetchAssetPools()
})
</script>

<style scoped>
.asset-pool-manager {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.asset-pool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.asset-pool-header h2 {
  margin: 0;
  font-size: 28px;
  color: #333;
  font-weight: 500;
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

.search-sort-container {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  gap: 10px;
  flex-wrap: wrap;
}

.sort-selector {
  display: flex;
  align-items: center;
  gap: 5px;
}

.sort-label {
  font-size: 14px;
  color: #666;
}

.asset-pool-list {
  margin-bottom: 30px;
}

.asset-pool-list h3 {
  margin-bottom: 20px;
  font-size: 20px;
  color: #333;
  font-weight: 500;
}

.asset-pool-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 15px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  background-color: white;
  border-radius: 8px;
  border: 1px dashed #dcdfe6;
  color: #909399;
}

.empty-state i {
  font-size: 48px;
  margin-bottom: 16px;
  color: #c0c4cc;
}

.empty-state p {
  margin-bottom: 20px;
  font-size: 14px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .asset-pool-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  
  .header-actions {
    width: 100%;
    justify-content: flex-start;
  }
  
  .search-sort-container {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  
  .asset-pool-cards {
    grid-template-columns: 1fr;
  }
}
</style>
