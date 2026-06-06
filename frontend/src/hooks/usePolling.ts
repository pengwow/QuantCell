/**
 * 通用轮询 Hook
 *
 * 替代各 tab 组件中手写的 setInterval 轮询逻辑，统一处理：
 * - 启用/暂停
 * - 浏览器 tab 可见性自动暂停
 * - 组件卸载清理
 * - 错误容忍（不中断轮询）
 *
 * 用法：
 *   usePolling(async () => {
 *     await fetchPositions(workerId)
 *   }, { interval: 5000, enabled: activeTab === 'positions' })
 */

import { useEffect, useRef } from 'react'

export interface UsePollingOptions {
  /** 轮询间隔（毫秒） */
  interval: number
  /** 是否启用轮询（默认 true） */
  enabled?: boolean
  /** 浏览器 tab 隐藏时是否暂停（默认 true） */
  pauseWhenHidden?: boolean
  /** 立即执行一次（默认 true） */
  immediate?: boolean
}

export const usePolling = (
  task: () => Promise<void> | void,
  options: UsePollingOptions
): void => {
  const { interval, enabled = true, pauseWhenHidden = true, immediate = true } = options

  // 用 ref 保存最新的 task，避免 task 变化时重启轮询
  const taskRef = useRef(task)
  taskRef.current = task

  useEffect(() => {
    if (!enabled) return

    let timer: ReturnType<typeof setTimeout> | null = null
    let isUnmounted = false

    const run = async () => {
      if (isUnmounted) return
      if (pauseWhenHidden && document.visibilityState !== 'visible') {
        schedule()
        return
      }
      try {
        await taskRef.current()
      } catch (err) {
        // 静默：单次失败不应中断轮询
        // eslint-disable-next-line no-console
        console.error('[usePolling] task error:', err)
      }
      schedule()
    }

    const schedule = () => {
      if (isUnmounted) return
      timer = setTimeout(run, interval)
    }

    // 浏览器切回可见时立即执行一次
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible' && !isUnmounted) {
        if (timer) clearTimeout(timer)
        run()
      }
    }

    if (pauseWhenHidden) {
      document.addEventListener('visibilitychange', onVisibilityChange)
    }

    if (immediate) {
      run()
    } else {
      schedule()
    }

    return () => {
      isUnmounted = true
      if (timer) clearTimeout(timer)
      if (pauseWhenHidden) {
        document.removeEventListener('visibilitychange', onVisibilityChange)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interval, enabled, pauseWhenHidden, immediate])
}
