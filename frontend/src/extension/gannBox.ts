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

// 离散豁免：江恩箱的箱体灰 / 对角线珊瑚红是装饰色，与 palette 语义槽位
// （chartMark #9ca3af / error #d1242f 等）均不等值，保留原值、集中到模块顶部便于后续并入离散调色板。
const GUIDE_STROKE = '#6C757D'
const DIAGONAL_STROKE = '#FF6B6B'

const gannBox: OverlayTemplate = {
  name: 'gannBox',
  totalStep: 2,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: false,
  needDefaultYAxisFigure: false,
  createPointFigures: ({ coordinates }) => {
    if (coordinates.length === 2) {
      const [startPoint, endPoint] = coordinates
      const width = Math.abs(endPoint.x - startPoint.x)
      const height = Math.abs(endPoint.y - startPoint.y)
      
      // 确定江恩箱的四个角
      const minX = Math.min(startPoint.x, endPoint.x)
      const minY = Math.min(startPoint.y, endPoint.y)
      const maxX = Math.max(startPoint.x, endPoint.x)
      const maxY = Math.max(startPoint.y, endPoint.y)
      
      const figures: OverlayFigure[] = []
      
      // 绘制江恩箱边框
      figures.push({
        type: 'polygon',
        attrs: {
          coordinates: [
            { x: minX, y: minY },
            { x: maxX, y: minY },
            { x: maxX, y: maxY },
            { x: minX, y: maxY }
          ]
        },
        styles: {
          style: 'stroke_fill',
          stroke: GUIDE_STROKE,
          strokeOpacity: 0.8,
          fill: GUIDE_STROKE,
          fillOpacity: 0.1
        }
      })
      
      // 绘制江恩箱内部的对角线
      figures.push({
        type: 'line',
        attrs: {
          coordinates: [
            { x: minX, y: minY },
            { x: maxX, y: maxY }
          ]
        },
        styles: {
          style: 'stroke',
          stroke: DIAGONAL_STROKE,
          strokeOpacity: 0.8,
          strokeDasharray: '5,5'
        }
      })
      
      figures.push({
        type: 'line',
        attrs: {
          coordinates: [
            { x: maxX, y: minY },
            { x: minX, y: maxY }
          ]
        },
        styles: {
          style: 'stroke',
          stroke: DIAGONAL_STROKE,
          strokeOpacity: 0.8,
          strokeDasharray: '5,5'
        }
      })
      
      // 绘制江恩箱的水平线和垂直线（1/8, 1/4, 3/8, 1/2, 5/8, 3/4, 7/8）
      const horizontalLines = [1/8, 1/4, 3/8, 1/2, 5/8, 3/4, 7/8]
      const verticalLines = [1/8, 1/4, 3/8, 1/2, 5/8, 3/4, 7/8]
      
      horizontalLines.forEach(ratio => {
        const y = minY + height * ratio
        figures.push({
          type: 'line',
          attrs: {
            coordinates: [
              { x: minX, y },
              { x: maxX, y }
            ]
          },
          styles: {
            style: 'stroke',
            stroke: GUIDE_STROKE,
            strokeOpacity: 0.6,
            strokeDasharray: '3,3'
          }
        })
      })
      
      verticalLines.forEach(ratio => {
        const x = minX + width * ratio
        figures.push({
          type: 'line',
          attrs: {
            coordinates: [
              { x, y: minY },
              { x, y: maxY }
            ]
          },
          styles: {
            style: 'stroke',
            stroke: GUIDE_STROKE,
            strokeOpacity: 0.6,
            strokeDasharray: '3,3'
          }
        })
      })
      
      return figures
    }
    return []
  }
}

export default gannBox