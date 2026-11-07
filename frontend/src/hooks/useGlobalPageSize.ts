/**
 * useGlobalPageSize - 全局分页大小
 *
 * 页面上的"每页条数"切换器即全站开关：
 * - 切换立即写入 configStore（所有订阅页面实时生效）
 * - 同时后台持久化到后端配置（失败仅提示，不回滚本地值）
 */
import { useCallback } from 'react';
import { App } from 'antd';
import { useConfigStore } from '../store/configStore';
import { configApi } from '../api';
import { snapPageSize } from '../constants/pagination';

export const useGlobalPageSize = (): [number, (size: number) => void] => {
  const { message } = App.useApp();
  // 精确订阅 defaultPerPage，避免 config 其他字段变化引起重渲染
  const stored = useConfigStore((s) => s.config?.defaultPerPage);

  const pageSize = snapPageSize(stored || 12);

  const setPageSize = useCallback(
    (size: number) => {
      const next = snapPageSize(size);
      const current = useConfigStore.getState().config;
      // 先本地生效（跨页实时同步），再后台持久化
      useConfigStore.getState().setConfig({ ...current, defaultPerPage: next });
      configApi
        .updateConfig([
          {
            key: 'defaultPerPage',
            value: String(next),
            name: 'general',
            description: '列表页默认显示数量',
          },
        ])
        .catch((err) => {
          console.error('[useGlobalPageSize] 持久化分页配置失败:', err);
          message.warning('分页配置保存失败，仅本次会话生效');
        });
    },
    [message]
  );

  return [pageSize, setPageSize];
};
