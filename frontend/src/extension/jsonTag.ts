/**
 * 支持JSON格式的标签组件，用于在图表上显示复杂样式的标签
 * 支持颜色设置、文本换行及其他复杂展示需求
 */
import type { OverlayTemplate } from 'klinecharts'

// 自定义实现isFunction函数
const isFunction = (value: unknown): value is Function => {
  return typeof value === 'function'
}

// 自定义实现isValid函数
const isValid = <T>(value: T | null | undefined): value is T => {
  return value !== null && value !== undefined
}

const jsonTag: OverlayTemplate = {
  name: 'jsonTag',
  totalStep: 2,
  styles: {
    line: { style: 'solid' }
  },
  createPointFigures: ({ overlay, coordinates }) => {
    let jsonData: any = { lines: [], colors: [], fontSize: 12, backgroundColor: 'rgba(255, 255, 255, 0.8)', borderColor: '#000000' }
    if (isValid(overlay.extendData)) {
      if (!isFunction(overlay.extendData)) {
        const extendData = overlay.extendData as string
        try {
          // 解析JSON数据
          jsonData = JSON.parse(extendData)
        } catch (e) {
          // 如果不是有效的JSON，作为普通文本处理
          jsonData = { lines: [extendData], colors: ['#000000'], fontSize: 12, backgroundColor: 'rgba(255, 255, 255, 0.8)', borderColor: '#000000' }
        }
      } else {
        // 如果extendData是函数，执行它获取结果
        const extendDataFunc = overlay.extendData as Function
        const result = extendDataFunc(overlay)
        if (typeof result === 'string') {
          try {
            jsonData = JSON.parse(result)
          } catch (e) {
            jsonData = { lines: [result], colors: ['#000000'], fontSize: 12, backgroundColor: 'rgba(255, 255, 255, 0.8)', borderColor: '#000000' }
          }
        } else {
          jsonData = result
        }
      }
    }

    // 设置默认值
    const lines = jsonData.lines || []
    const colors = jsonData.colors || []
    const fontSize = jsonData.fontSize || 12
    const backgroundColor = jsonData.backgroundColor || 'rgba(255, 255, 255, 0.8)'
    const borderColor = jsonData.borderColor || '#000000'
    const padding = jsonData.padding || 5
    const borderRadius = jsonData.borderRadius || 3
    
    const startX = coordinates[0].x
    const startY = coordinates[0].y

    // 计算文本元素
    let textY = startY - 10
    const textElements: any[] = []
    let maxTextWidth = 0
    
    // 为每行文本创建一个text元素并计算最大宽度
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      const color = colors[i] || colors[colors.length - 1] || '#000000'
      
      textElements.push({
        type: 'text',
        attrs: {
          x: startX,
          y: textY,
          text: line,
          align: 'center',
          baseline: 'middle',
          color: color,
          fontSize: fontSize
        },
        ignoreEvent: true
      })
      
      // 计算文本宽度（估算，实际渲染时可能需要调整）
      const textWidth = line.length * fontSize * 0.6
      if (textWidth > maxTextWidth) {
        maxTextWidth = textWidth
      }
      
      // 每行文本间距为fontSize的1.2倍
      textY += fontSize * 1.2
    }
    
    // 计算背景框尺寸
    const boxWidth = maxTextWidth + padding * 2
    const boxHeight = lines.length * fontSize * 1.2 + padding * 2
    const boxStartX = startX - boxWidth / 2
    const boxStartY = startY - (lines.length * fontSize * 1.2) / 2 - padding
    
    return [
      {
        type: 'rect',
        attrs: {
          x: boxStartX,
          y: boxStartY,
          width: boxWidth,
          height: boxHeight,
          radius: borderRadius
        },
        styles: {
          fill: backgroundColor,
          stroke: borderColor,
          lineWidth: 1
        },
        ignoreEvent: true
      },
      ...textElements
    ]
  }
}

export default jsonTag