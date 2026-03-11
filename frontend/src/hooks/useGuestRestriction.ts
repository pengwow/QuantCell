/**
 * 访客权限限制 Hook
 * 用于检查当前用户是否为访客，并提供相应的限制功能
 */
import { useMemo, useCallback } from 'react';
import { message, Modal } from 'antd';
import { useNavigate } from 'react-router-dom';
import { isGuestUser, getRestrictedFeatureMessage } from '../utils/roleManager';

interface UseGuestRestrictionReturn {
  /** 是否为访客用户 */
  isGuest: boolean;
  /** 检查是否有权限执行操作，如果没有则显示提示 */
  checkPermission: (action?: string) => boolean;
  /** 显示登录提示对话框 */
  showLoginModal: (title?: string, content?: string) => void;
  /** 获取按钮的禁用状态 */
  getButtonDisabled: () => boolean;
  /** 获取按钮的提示文本 */
  getButtonTooltip: () => string | undefined;
}

/**
 * 访客权限限制 Hook
 * @returns 权限检查相关的方法和状态
 */
export const useGuestRestriction = (): UseGuestRestrictionReturn => {
  const navigate = useNavigate();
  
  const isGuest = useMemo(() => isGuestUser(), []);

  /**
   * 检查是否有权限执行操作
   * @param action 操作描述
   * @returns 是否有权限
   */
  const checkPermission = useCallback((action?: string): boolean => {
    if (isGuest) {
      const msg = action 
        ? `访客用户无法${action}，请使用普通用户账号登录`
        : getRestrictedFeatureMessage();
      message.warning(msg);
      return false;
    }
    return true;
  }, [isGuest]);

  /**
   * 显示登录提示对话框
   */
  const showLoginModal = useCallback((title?: string, content?: string) => {
    Modal.warning({
      title: title || '功能受限',
      content: content || getRestrictedFeatureMessage(),
      okText: '去登录',
      onOk: () => {
        navigate('/login');
      },
    });
  }, [navigate]);

  /**
   * 获取按钮的禁用状态
   */
  const getButtonDisabled = useCallback((): boolean => {
    return isGuest;
  }, [isGuest]);

  /**
   * 获取按钮的提示文本
   */
  const getButtonTooltip = useCallback((): string | undefined => {
    return isGuest ? getRestrictedFeatureMessage() : undefined;
  }, [isGuest]);

  return {
    isGuest,
    checkPermission,
    showLoginModal,
    getButtonDisabled,
    getButtonTooltip,
  };
};

export default useGuestRestriction;
