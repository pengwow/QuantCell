<template>
  <div class="asset-list">
    <!-- 资产列表 -->
    <div class="assets-section">
      <div class="assets-header">
        <h4>资产列表 ({{ assets.length }}个资产)</h4>
      </div>

      <!-- 资产列表表格 -->
      <el-table 
        v-if="assets.length > 0" 
        :data="assets.map(asset => ({ asset }))" 
        size="mini"
        style="width: 100%;"
      >
        <el-table-column prop="asset" label="资产代码" width="120"></el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="scope">
            <el-button 
              type="danger" 
              size="mini"
              @click="handleRemoveAsset(scope.row.asset)"
              icon="el-icon-delete"
            ></el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 空状态 -->
      <div v-else class="empty-assets">
        <el-empty description="暂无资产" :image-size="60"></el-empty>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import axios from 'axios'

// 定义组件属性
const props = defineProps<{
  poolId: number
  assets: string[]
  assetType: string
}>()

// 定义事件
const emit = defineEmits<{
  update: []
}>()

// 处理单个资产移除
const handleRemoveAsset = async (asset: string) => {
  try {
    // 调用API从资产池移除资产
    await axios.delete(`/api/data-pools/${props.poolId}/assets`, {
      data: { assets: [asset] }
    })

    ElMessage.success('资产移除成功')
    emit('update')
  } catch (error: any) {
    ElMessage.error(`移除资产失败: ${error.message}`)
  }
}
</script>

<style scoped>
.asset-list {
  padding: 15px;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.assets-section {
  margin-top: 0;
}

.assets-header {
  margin-bottom: 15px;
}

.assets-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.empty-assets {
  padding: 20px;
  text-align: center;
}
</style>
