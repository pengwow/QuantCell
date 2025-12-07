<template>
  <div class="asset-pool-form">
    <el-form 
      ref="formRef" 
      :model="formData" 
      label-width="100px"
      size="small"
    >
      <!-- 基本信息 -->
      <el-form-item label="名称" prop="name" required>
        <el-input 
          v-model="formData.name" 
          placeholder="请输入资产池名称"
          maxlength="50"
          show-word-limit
          autocomplete="off"
          spellcheck="false"
        ></el-input>
      </el-form-item>

      <el-form-item label="类型" prop="type" required>
        <el-select 
          v-model="formData.type" 
          placeholder="请选择资产池类型"
        >
          <el-option label="加密货币" value="crypto"></el-option>
          <el-option label="股票" value="stock"></el-option>
        </el-select>
      </el-form-item>

      <el-form-item label="描述">
        <el-input 
          v-model="formData.description" 
          type="textarea" 
          :rows="3" 
          placeholder="请输入资产池描述"
          maxlength="200"
          show-word-limit
          autocomplete="off"
          spellcheck="false"
        ></el-input>
      </el-form-item>

      <!-- 操作按钮 -->
      <el-form-item style="text-align: right;">
        <el-button size="small" @click="handleCancel">取消</el-button>
        <el-button type="primary" size="small" @click="handleSubmit">保存</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

// 定义组件属性
const props = defineProps<{
  pool: {
    id?: number
    name?: string
    type?: string
    description?: string
    color?: string
    tags?: string
    created_at?: string
    updated_at?: string
  }
  isEditing?: boolean
}>()

// 定义事件
const emit = defineEmits<{
  submit: [poolData: typeof props.pool]
  cancel: []
}>()

// 表单引用
const formRef = ref<any>(null)

// 响应式数据
const formData = reactive({
  name: '',
  type: 'crypto',
  description: '',
  tags: '[]'
})

// 监听props变化，更新表单数据
watch(() => props.pool, (newPool) => {
  formData.name = newPool.name || ''
  formData.type = newPool.type || 'crypto'
  formData.description = newPool.description || ''
}, { immediate: true, deep: true })

// 提交表单
const handleSubmit = () => {
  // 验证表单数据
  if (!formData.name.trim()) {
    ElMessage.warning('请输入资产池名称')
    return
  }

  if (!formData.type) {
    ElMessage.warning('请选择资产池类型')
    return
  }

  // 构建提交数据
  const submitData = {
    ...formData
  }

  // 如果是编辑模式，保留id
  if (props.isEditing && 'id' in props.pool && props.pool.id) {
    (submitData as any).id = props.pool.id
  }

  // 提交表单
  emit('submit', submitData)
}

// 取消操作
const handleCancel = () => {
  emit('cancel')
}
</script>

<style scoped>
.asset-pool-form {
  padding: 20px 0;
}

.color-picker-container {
  display: flex;
  align-items: center;
  gap: 15px;
  flex-wrap: wrap;
}

.preset-colors {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.color-preset {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.3s ease;
}

.color-preset:hover {
  transform: scale(1.1);
}

.color-preset.active {
  border-color: #409EFF;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.custom-color {
  flex: 1;
  min-width: 150px;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.tag-input {
  width: 120px;
  margin-top: 8px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .color-picker-container {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .custom-color {
    width: 100%;
  }
}
</style>
