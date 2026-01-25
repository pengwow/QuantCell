/**
 * 支持JSON格式的注解组件，用于回测回放页面的交易标记
 * 支持颜色设置、文本换行及复杂展示需求
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

// 可扩展的颜色配置
const COLOR_CONFIG = {
  buy: '#26a666ff', // 多单绿色
  sell: '#ff0400ff', // 空单红色
  default: '#ffffff', // 默认白色文字
  background: '#1e88e5', // 深蓝色背景色，带透明度
  border: '#1e88e5', // 边框色
  line: '#bdbdbd' // 连接线色
}

// 颜色切换映射（用于快速转换）- 用于绿色与红色的快速转换功能
const COLOR_SWITCH_MAP = {
  '#26a69a': '#ef5350',
  '#ef5350': '#26a69a'
}

/**
 * 颜色切换函数 - 用于快速转换绿色和红色
 * @param color 当前颜色
 * @returns 切换后的颜色
 */
export const switchColor = (color: string): string => {
  return COLOR_SWITCH_MAP[color as keyof typeof COLOR_SWITCH_MAP] || color
}

const jsonAnnotation: OverlayTemplate = {
  name: 'jsonAnnotation',
  totalStep: 2,
  styles: {
    line: { style: 'dashed' }
  },
  createPointFigures: ({ overlay, coordinates }) => {
    let jsonData: any = { 
      lines: [], 
      colors: [], 
      fontSize: 12,
      align: 'center', // 新增：对齐方式，默认居中
      type: 'default', // 新增：注解类型，默认普通
      padding: 8, // 新增：内边距
      backgroundColor: COLOR_CONFIG.background, // 新增：背景色
      borderColor: COLOR_CONFIG.border, // 新增：边框色
      borderRadius: 4 // 新增：圆角
    }
    
    if (isValid(overlay.extendData)) {
      if (!isFunction(overlay.extendData)) {
        const extendData = overlay.extendData as string
        try {
          // 解析JSON数据
          jsonData = JSON.parse(extendData)
        } catch (e) {
          // 如果不是有效的JSON，作为普通文本处理
          jsonData = { 
            lines: [extendData], 
            colors: ['#000000'], 
            fontSize: 12,
            align: 'center',
            type: 'default'
          }
        }
      } else {
        // 如果extendData是函数，执行它获取结果
        const extendDataFunc = overlay.extendData as Function
        const result = extendDataFunc(overlay)
        if (typeof result === 'string') {
          try {
            jsonData = JSON.parse(result)
          } catch (e) {
            jsonData = { 
              lines: [result], 
              colors: ['#000000'], 
              fontSize: 12,
              align: 'center',
              type: 'default'
            }
          }
        } else {
          jsonData = result
        }
      }
    }

    // 设置默认值
    let lines = jsonData.lines || []
    let colors = jsonData.colors || []
    const fontSize = jsonData.fontSize || 12
    const align = jsonData.align || 'center' // 新增：对齐方式
    const type = jsonData.type || 'default' // 新增：注解类型
    const padding = jsonData.padding || 3 // 新增：内边距
    const backgroundColor = jsonData.backgroundColor || COLOR_CONFIG.background // 新增：背景色
    const borderColor = jsonData.borderColor || COLOR_CONFIG.border // 新增：边框色
    const borderRadius = jsonData.borderRadius || 4 // 新增：圆角
    
    // 完善字体颜色实现：根据注解类型设置默认颜色
    if (colors.length === 0) {
      // 如果没有指定颜色，根据类型设置
      colors = lines.map(() => {
        switch (type) {
          case 'buy':
            return COLOR_CONFIG.buy
          case 'sell':
            return COLOR_CONFIG.sell
          default:
            return COLOR_CONFIG.default
        }
      })
    } else {
      // 如果指定了部分颜色，补充完整
      while (colors.length < lines.length) {
        colors.push(colors[colors.length - 1] || COLOR_CONFIG.default)
      }
    }
    
    // 解析背景色的透明度，应用到文字颜色上，确保透明度一致
    const parseBackgroundColor = (bgColor: string) => {
      // 处理rgba格式
      if (bgColor.startsWith('rgba(')) {
        const match = bgColor.match(/rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)/)
        if (match) {
          return parseFloat(match[4])
        }
      }
      // 处理hex格式（#RRGGBBAA）
      if (bgColor.length === 9 && bgColor.startsWith('#')) {
        const alphaHex = bgColor.slice(7, 9)
        return parseInt(alphaHex, 16) / 255
      }
      // 处理hex格式（#RGBA）
      if (bgColor.length === 5 && bgColor.startsWith('#')) {
        const alphaHex = bgColor.slice(4, 5)
        return parseInt(alphaHex + alphaHex, 16) / 255
      }
      // 默认不透明
      return 1
    }
    
    // 处理文字颜色，确保透明度与背景色一致
    const bgAlpha = parseBackgroundColor(backgroundColor)
    if (bgAlpha < 1) {
      // 如果背景色有透明度，将透明度应用到文字颜色上
      const applyAlphaToColor = (color: string, alpha: number) => {
        // 处理rgba格式
        if (color.startsWith('rgba(')) {
          return color.replace(/rgba\((\d+),\s*(\d+),\s*(\d+),\s*[\d.]+\)/, `rgba($1, $2, $3, ${alpha})`)
        }
        // 处理rgb格式
        if (color.startsWith('rgb(')) {
          return color.replace(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/, `rgba($1, $2, $3, ${alpha})`)
        }
        // 处理hex格式
        if (color.startsWith('#')) {
          // 转换hex到rgba
          const hex = color.replace('#', '')
          let r, g, b
          if (hex.length === 3) {
            r = parseInt(hex[0] + hex[0], 16)
            g = parseInt(hex[1] + hex[1], 16)
            b = parseInt(hex[2] + hex[2], 16)
          } else {
            r = parseInt(hex.slice(0, 2), 16)
            g = parseInt(hex.slice(2, 4), 16)
            b = parseInt(hex.slice(4, 6), 16)
          }
          return `rgba(${r}, ${g}, ${b}, ${alpha})`
        }
        return color
      }
      
      // 应用透明度到所有文字颜色
      colors = colors.map((color: string) => applyAlphaToColor(color, bgAlpha))
    }
    
    // 计算文本宽度（估算）
    const calculateTextWidth = (text: string) => {
      return text.length * fontSize * 0.6
    }
    
    // 找到最长行的宽度
    let maxTextWidth = 0
    lines.forEach((line: string) => {
      const width = calculateTextWidth(line)
      if (width > maxTextWidth) {
        maxTextWidth = width
      }
    })
    
    // 计算行高 - 增加行高以避免重叠，使用1.4倍字体大小
    const lineHeight = fontSize * 1.4
    const totalHeight = lines.length * lineHeight + padding * 2
    
    // 计算起始坐标
    const startX = coordinates[0].x
    const startY = coordinates[0].y - 6
    const lineEndY = startY - 10 - totalHeight // 调整连接线长度
    const arrowEndY = lineEndY - 5
    
    // 计算背景框坐标 - 始终居中显示
    const boxWidth = maxTextWidth + padding * 2
    // 固定背景框始终居中
    const boxStartX = startX - boxWidth / 2
    const boxStartY = arrowEndY - totalHeight
    
    // 计算文本起始Y坐标 - 从背景框顶部开始往下排列，确保数组顺序与显示顺序一致
    let textY = boxStartY + padding + lineHeight / 2
    const textElements: any[] = []
    
    // 计算每行文本的X坐标（根据对齐方式在背景框内部对齐）
    let textX: number
    switch (align) {
      case 'left':
        // 文字在背景框内左对齐
        textX = boxStartX + padding
        break
      case 'right':
        // 文字在背景框内右对齐
        textX = boxStartX + boxWidth - padding
        break
      case 'center':
      default:
        // 文字在背景框内居中对齐
        textX = boxStartX + boxWidth / 2
        break
    }

    // 为每行文本创建一个text元素 - 仅设置文字颜色，无背景色
    // 从顶部到底部绘制，数组第一个元素显示在最上方
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      // 文字颜色通过colors数组自定义，支持不同行使用不同颜色
      const color = colors[i] || COLOR_CONFIG.default
      
      textElements.push({
        type: 'text',
        attrs: {
          x: textX,
          y: textY,
          text: line,
          align: align,
          baseline: 'middle',
          color: color, // 仅设置文字颜色
          fontSize: fontSize
        },
        styles: {
          // 参考KLineChart的TextStyle，设置style为fill，无背景色
          style: 'fill',
          color: color, // 仅设置文字颜色
          // 明确设置背景色为透明，确保没有背景
          backgroundColor: 'transparent',
          // 无边框
          borderSize: 0,
          borderColor: 'transparent'
        },
        ignoreEvent: true
      })
      
      // 每行文本间距为fontSize的1.4倍，从上往下递增
      textY += lineHeight
    }

    return [
      {
        type: 'line',
        attrs: { coordinates: [{ x: startX, y: startY }, { x: startX, y: lineEndY }] },
        styles: {
          stroke: COLOR_CONFIG.line
        },
        ignoreEvent: true
      },
      {
        type: 'polygon',
        attrs: { coordinates: [{ x: startX, y: lineEndY }, { x: startX - 4, y: arrowEndY }, { x: startX + 4, y: arrowEndY }] },
        styles: {
          // fill: COLOR_CONFIG.line
        },
        ignoreEvent: true
      },
      // 新增：背景框
      {
        type: 'rect',
        attrs: {
          x: boxStartX,
          y: boxStartY,
          width: boxWidth,
          height: totalHeight,
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

export default jsonAnnotation