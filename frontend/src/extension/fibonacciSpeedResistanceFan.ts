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

import type { OverlayTemplate } from 'klinecharts'

const fibonacciSpeedResistanceFan: OverlayTemplate = {
  name: 'fibonacciSpeedResistanceFan',
  totalStep: 2,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates, bounding }) => {
    if (coordinates.length === 2) {
      const [startPoint, endPoint] = coordinates
      const startValue = startPoint.y
      const endValue = endPoint.y
      
      // 斐波那契速度阻力扇形线比例
      const levels = [0, 0.382, 0.5, 0.618, 1]
      const lines: any[] = []
      const texts: any[] = []
      
      levels.forEach(level => {
        const value = startValue + (endValue - startValue) * level
        const lineEnd = {
          x: endPoint.x,
          y: value
        }
        
        // 计算射线
        const dx = lineEnd.x - startPoint.x
        const dy = lineEnd.y - startPoint.y
        const rayLine = [
          startPoint,
          {
            x: bounding.right + dx * 100,
            y: lineEnd.y + dy * 100
          }
        ]
        
        lines.push({
          type: 'line',
          attrs: { coordinates: rayLine },
          styles: {
            style: 'stroke',
            stroke: '#6C757D',
            strokeOpacity: 0.8,
            strokeDasharray: '5,5'
          }
        })
        
        // 添加文本标签
        const textX = bounding.right + 5
        texts.push({
          type: 'text',
          attrs: {
            x: textX,
            y: lineEnd.y,
            text: `${(level * 100).toFixed(0)}%`
          },
          styles: {
            textFill: '#6C757D',
            fontSize: 10,
            textAlign: 'start',
            textBaseline: 'middle'
          }
        })
      })
      
      return [...lines, ...texts]
    }
    return []
  }
}

export default fibonacciSpeedResistanceFan