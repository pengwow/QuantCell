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

import type { Coordinate, Bounding, LineAttrs } from 'klinecharts'
import { utils } from 'klinecharts'

/**
 * 获取旋转后的坐标点
 * @param coordinate 坐标点
 * @param center 旋转中心点
 * @param offsetAngle 旋转角度，单位弧度
 * @returns 旋转后的坐标点
 */
export function getRotateCoordinate(coordinate: Coordinate, center: Coordinate, offsetAngle: number): Coordinate {
  const x = coordinate.x - center.x
  const y = coordinate.y - center.y
  return {
    x: Math.cos(offsetAngle) * x - Math.sin(offsetAngle) * y + center.x,
    y: Math.sin(offsetAngle) * x + Math.cos(offsetAngle) * y + center.y
  }
}

/**
 * 计算斐波那契回调线
 * @param startValue 起始值
 * @param endValue 结束值
 * @returns 斐波那契回调线值数组
 */
export function calculateFibonacciRetracements(startValue: number, endValue: number): number[] {
  const isRising = endValue > startValue
  const high = Math.max(startValue, endValue)
  const low = Math.min(startValue, endValue)
  const diff = high - low

  const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
  return levels.map(level => {
    const value = isRising ? high - diff * level : low + diff * level
    return parseFloat(value.toFixed(8))
  })
}

/**
 * 计算斐波那契扩展线
 * @param startValue 起始值
 * @param endValue 结束值
 * @returns 斐波那契扩展线值数组
 */
export function calculateFibonacciExtensions(startValue: number, _midValue: number, endValue: number): number[] {
  const isRising = endValue > startValue
  const diff = Math.abs(endValue - startValue)
  const levels = [0, 0.618, 1, 1.618, 2.618]
  return levels.map(level => {
    const value = isRising ? endValue + diff * level : endValue - diff * level
    return parseFloat(value.toFixed(8))
  })
}

/**
 * 计算两点之间的距离
 * @param coordinate1 坐标点1
 * @param coordinate2 坐标点2
 * @returns 距离
 */
export function calculateDistance(coordinate1: Coordinate, coordinate2: Coordinate): number {
  const dx = coordinate2.x - coordinate1.x
  const dy = coordinate2.y - coordinate1.y
  return Math.sqrt(dx * dx + dy * dy)
}

/**
 * 计算两点之间的角度
 * @param coordinate1 坐标点1
 * @param coordinate2 坐标点2
 * @returns 角度，单位弧度
 */
export function calculateAngle(coordinate1: Coordinate, coordinate2: Coordinate): number {
  return Math.atan2(coordinate2.y - coordinate1.y, coordinate2.x - coordinate1.x)
}

/**
 * 生成射线
 * @param start 起点
 * @param end 终点
 * @param length 射线长度
 * @returns 射线的两个端点坐标
 */
export function getRayLine(start: Coordinate, end: Coordinate, length: number = 1000): Coordinate[] {
  const dx = end.x - start.x
  const dy = end.y - start.y
  const distance = Math.sqrt(dx * dx + dy * dy)
  const scale = length / distance
  
  return [
    start,
    {
      x: end.x + dx * scale,
      y: end.y + dy * scale
    }
  ]
}

/**
 * 检查坐标是否在线段上
 * @param coordinate 坐标点
 * @param lineAttrs 线段属性
 * @returns 是否在线段上
 */
export function isCoordinateOnLine(coordinate: Coordinate, lineAttrs: LineAttrs): boolean {
  const { coordinates } = lineAttrs
  if (coordinates.length < 2) return false

  for (let i = 0; i < coordinates.length - 1; i++) {
    const start = coordinates[i]
    const end = coordinates[i + 1]
    const distance = utils.checkCoordinateOnLine(coordinate, { coordinates: [start, end] })
    if (distance) return true
  }
  return false
}

/**
 * 计算矩形边界
 * @param coordinates 坐标点数组
 * @returns 边界
 */
export function calculateBounding(coordinates: Coordinate[]): Bounding {
  if (coordinates.length === 0) {
    return { width: 0, height: 0, left: 0, right: 0, top: 0, bottom: 0 }
  }

  const minX = Math.min(...coordinates.map(c => c.x))
  const maxX = Math.max(...coordinates.map(c => c.x))
  const minY = Math.min(...coordinates.map(c => c.y))
  const maxY = Math.max(...coordinates.map(c => c.y))

  return {
    width: maxX - minX,
    height: maxY - minY,
    left: minX,
    right: maxX,
    top: minY,
    bottom: maxY
  }
}

// 别名，保持与原代码兼容
export const getDistance = calculateDistance