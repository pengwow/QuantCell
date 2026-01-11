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

const abcd: OverlayTemplate = {
  name: 'abcd',
  totalStep: 4,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates }) => {
    if (coordinates.length === 4) {
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
            stroke: '#FFA500',
            strokeOpacity: 0.8,
            strokeWidth: 1,
            fill: '#FFA500',
            fillOpacity: 0.2
          }
        }
      ]
    }
    return []
  }
}

export default abcd