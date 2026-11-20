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

// 离散豁免：形态（XABCD）三角形的橙色描边/填充是装饰色，与 palette 语义槽位
// （primary #ea580c / error #d1242f 等）均不等值，保留原值、集中到模块顶部便于后续并入离散调色板。
const PATTERN_FILL = '#FFA500'

const xabcd: OverlayTemplate = {
  name: 'xabcd',
  totalStep: 5,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates }) => {
    if (coordinates.length === 5) {
      return [
        {
          type: 'line',
          attrs: { coordinates }
        },
        {
          type: 'polygon',
          attrs: {
            coordinates: [coordinates[1], coordinates[2], coordinates[3]]
          },
          styles: {
            style: 'stroke_fill',
            stroke: PATTERN_FILL,
            strokeOpacity: 0.8,
            strokeWidth: 1,
            fill: PATTERN_FILL,
            fillOpacity: 0.2
          }
        }
      ]
    }
    return []
  }
}

export default xabcd