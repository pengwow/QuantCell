/**
 * 统一的详情页返回逻辑：URL 带 returnUrl 时优先返回该地址（保留列表页的
 * 筛选/分页状态），否则走浏览器历史返回。回测详情/配置/回放等子页面共用，
 * 与原先 BacktestLayout 顶部返回按钮的行为完全一致。
 */
import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export function usePageBack() {
  const navigate = useNavigate();
  const location = useLocation();

  return useCallback(() => {
    const returnUrl = new URLSearchParams(location.search).get('returnUrl');
    if (returnUrl) navigate(decodeURIComponent(returnUrl));
    else navigate(-1);
  }, [navigate, location.search]);
}
