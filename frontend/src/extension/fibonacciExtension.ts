/**
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at

 * http://www.apache.org/licenses/LICENSE-2.0

 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import type { OverlayFigure, OverlayTemplate } from 'klinecharts'

import { calculateFibonacciExtensions } from './utils'

// 离散豁免：斐波那契工具的水平线灰与主趋势珊瑚红是装饰色，与 palette 语义槽位
// （chartMark #9ca3af / error #d1242f 等）均不等值，保留原值、集中到模块顶部便于后续并入离散调色板。
const LEVEL_STROKE = '#6C757D'
const TREND_STROKE = '#FF6B6B'

const fibonacciExtension: OverlayTemplate = {
  name: 'fibonacciExtension',
  totalStep: 3,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates, bounding }) => {
    if (coordinates.length === 3) {
      const [startPoint, midPoint, endPoint] = coordinates
      const startValue = startPoint.y
      const midValue = midPoint.y
      const endValue = endPoint.y
      
      const fibonacciLevels = calculateFibonacciExtensions(startValue, midValue, endValue)
      const levels = [0, 0.618, 1, 1.618, 2.618]
      const figures: OverlayFigure[] = []
      
      fibonacciLevels.forEach((level, index) => {
        // 绘制水平线
        figures.push({
          type: 'line',
          attrs: {
            coordinates: [
              { x: bounding.left, y: level },
              { x: bounding.right, y: level }
            ]
          },
          styles: {
            style: 'stroke',
            stroke: LEVEL_STROKE,
            strokeOpacity: 0.8,
            strokeDasharray: '5,5'
          }
        })
        
        // 添加文本标签
        figures.push({
          type: 'text',
          attrs: {
            x: bounding.right + 5,
            y: level,
            text: `${levels[index] === 0 ? '0' : levels[index]}`
          },
          styles: {
            textFill: LEVEL_STROKE,
            fontSize: 10,
            textAlign: 'start',
            textBaseline: 'middle'
          }
        })
      })
      
      // 绘制主趋势线
      figures.push({
        type: 'line',
        attrs: {
          coordinates: [startPoint, endPoint]
        },
        styles: {
          style: 'stroke',
          stroke: TREND_STROKE,
          strokeOpacity: 0.8
        }
      })
      
      return figures
    }
    return []
  }
}

export default fibonacciExtension