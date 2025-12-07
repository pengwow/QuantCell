<template>
  <div 
    class="asset-pool-card"
  >
    <!-- 卡片头部 -->
    <div class="card-header">
      <h3 class="pool-name">{{ pool.name }}</h3>
      <span class="status-badge" :class="`status-${pool.type}`">
        {{ pool.type === 'stock' ? '股票' : '加密货币' }}
      </span>
    </div>

    <!-- 卡片内容 -->
    <div class="card-body">
      <p class="pool-description" v-if="pool.description">{{ pool.description }}</p>
      <p class="pool-description empty" v-else>暂无描述</p>
      <div class="pool-tags">
        <el-tag 
          v-for="tag in poolTags" 
          :key="tag" 
          size="mini"
          effect="light"
        >
          {{ tag }}
        </el-tag>
      </div>
      <div class="pool-meta">
        <span class="meta-item">
          <i class="el-icon-document-copy"></i>
          {{ pool.asset_count }} 个资产
        </span>
        <span class="meta-item">
          <i class="el-icon-date"></i>
          {{ formatDate(pool.created_at) }}
        </span>
      </div>
    </div>

    <!-- 卡片底部 -->
    <div class="card-footer">
      <el-button 
        type="text" 
        size="small"
        @click="isExpanded = !isExpanded"
      >
        <i :class="isExpanded ? 'el-icon-caret-top' : 'el-icon-caret-bottom'"></i>
        {{ isExpanded ? '收起' : '展开' }}
      </el-button>
      <el-dropdown @command="handleAction" trigger="click">
        <el-button type="primary" size="small">
          操作
          <i class="el-icon-arrow-down el-icon--right"></i>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="addAsset">添加资产</el-dropdown-item>
            <el-dropdown-item command="edit">编辑</el-dropdown-item>
            <el-dropdown-item command="delete">删除</el-dropdown-item>
            <el-dropdown-item command="copy">复制</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 展开的资产列表 -->
    <div v-if="isExpanded" class="card-assets">
      <asset-list
        :pool-id="pool.id"
        :assets="pool.assets || []"
        :asset-type="pool.type"
        @update="handleAssetsUpdate"
      ></asset-list>
    </div>

    <!-- 添加资产模态框 -->
    <el-dialog
      v-model="addAssetDialogVisible"
      title="添加资产"
      width="400px"
      append-to-body
    >
      <el-form :model="addAssetForm" label-width="100px" size="small">
        <el-form-item label="资产代码">
          <el-input
            v-model="addAssetForm.assetCode"
            placeholder="输入资产代码（如: BTCUSDT 或 AAPL）"
            clearable
            @keyup.enter="handleAddAsset"
            autocomplete="off"
            spellcheck="false"
          ></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="addAssetDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleAddAsset">添加</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import AssetList from './AssetList.vue'

// 定义组件属性
const props = defineProps<{
  pool: {
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
}>()

// 定义事件
const emit = defineEmits<{
  edit: [pool: typeof props.pool]
  delete: [poolId: number]
  expand: [poolId: number]
  update: []
}>()

// 响应式数据
const isExpanded = ref(false)
const addAssetDialogVisible = ref(false)
const addAssetForm = ref({
  assetCode: ''
})

// 计算属性：解析标签
const poolTags = computed(() => {
  try {
    return props.pool.tags ? JSON.parse(props.pool.tags) : []
  } catch (e) {
    return []
  }
})

// 格式化日期
const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString()
}

// 处理卡片操作
const handleAction = (command: string) => {
  switch (command) {
    case 'addAsset':
      addAssetDialogVisible.value = true
      break
    case 'edit':
      emit('edit', props.pool)
      break
    case 'delete':
      handleDelete()
      break
    case 'copy':
      handleCopy()
      break
    default:
      break
  }
}

// 处理添加资产
const handleAddAsset = async () => {
  const assetCode = addAssetForm.value.assetCode.trim().toUpperCase()
  if (!assetCode) {
    ElMessage.warning('请输入资产代码')
    return
  }

  // 检查资产是否已存在
  if ((props.pool.assets || []).includes(assetCode)) {
    ElMessage.warning('该资产已存在')
    return
  }

  try {
    // 调用API添加资产
    await axios.post(`/api/data-pools/${props.pool.id}/assets`, {
      assets: [assetCode],
      asset_type: props.pool.type
    })

    ElMessage.success('资产添加成功')
    addAssetDialogVisible.value = false
    addAssetForm.value.assetCode = ''
    emit('update')
  } catch (error: any) {
    ElMessage.error(`添加资产失败: ${error.message}`)
  }
}

// 处理删除资产池
const handleDelete = () => {
  ElMessageBox.confirm(
    `确定要删除资产池 "${props.pool.name}" 吗？此操作不可恢复。`,
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    emit('delete', props.pool.id)
  }).catch(() => {
    // 取消删除操作
  })
}

// 处理复制资产池
const handleCopy = () => {
  ElMessage.info('复制功能开发中...')
}

// 处理资产更新
const handleAssetsUpdate = () => {
  emit('update')
}
</script>

<style scoped>
.asset-pool-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border: 1px solid #e0e0e0;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.asset-pool-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
  padding: 20px;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
  font-weight: 500;
}

.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  margin-top: 2px;
}

.status-stock {
  background-color: #d4edda;
  color: #155724;
}

.status-crypto {
  background-color: #cce7ff;
  color: #004085;
}

.card-body {
  padding: 0 20px 20px 20px;
}

.card-body .pool-description {
  margin: 0 0 15px 0;
  color: #666;
  font-size: 14px;
  line-height: 1.5;
}

.pool-description.empty {
  color: #999;
  font-style: italic;
}

.pool-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 15px;
  flex-wrap: wrap;
}

.pool-tags .el-tag {
  font-size: 12px;
  padding: 2px 8px;
}

.pool-meta {
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

.meta-item i {
  font-size: 12px;
}

.card-footer {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  align-items: center;
  margin-top: 15px;
  padding: 15px 20px;
  border-top: 1px solid #f0f0f0;
}

.card-footer .el-button {
  font-size: 12px;
  padding: 4px 12px;
}

.card-assets {
  padding: 0 20px 20px 20px;
  border-top: 1px solid #f0f0f0;
  background-color: white;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .asset-pool-card {
    margin-bottom: 16px;
  }
  
  .card-footer {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  
  .card-footer .el-button {
    width: 100%;
  }
}
</style>
