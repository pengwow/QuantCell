/**
 * usePermission - 权限检查 Hook
 * 用于控制用户对日志设置功能的访问权限
 */
import { useState, useEffect } from 'react';

// 模拟的用户权限列表（实际应从API或Context获取）
const MOCK_USER_PERMISSIONS = [
  'logs:read',
  // 管理员拥有所有权限
  // 'logs:delete',
  // 'logs:config',
];

/**
 * 权限检查 Hook
 * @param permission 需要检查的权限标识
 * @returns 是否拥有该权限
 *
 * 使用示例：
 * const canDelete = usePermission('logs:delete');
 * if (canDelete) { <Button danger>删除</Button> }
 */
export function usePermission(permission: string): boolean {
  const [hasPermission, setHasPermission] = useState(false);

  useEffect(() => {
    // 实际项目中应该从以下位置获取权限：
    // 1. 用户登录信息中的角色/权限字段
    // 2. API接口动态获取
    // 3. Redux/Zustand 全局状态管理

    // 当前使用模拟数据（默认允许读取，需要管理员权限才能删除/配置）
    const isAdmin = true; // TODO: 替换为实际的管理员判断逻辑
    const userPermissions = isAdmin
      ? [...MOCK_USER_PERMISSIONS, 'logs:delete', 'logs:config']
      : MOCK_USER_PERMISSIONS;

    setHasPermission(
      userPermissions.includes(permission) ||
      userPermissions.includes('admin')
    );
  }, [permission]);

  return hasPermission;
}

/**
 * 多权限检查 Hook
 * @param permissions 需要检查的权限列表
 * @param mode 检查模式：'every' (全部满足) | 'some' (满足其一)
 * @returns 是否满足条件
 */
export function usePermissions(
  permissions: string[],
  mode: 'every' | 'some' = 'every'
): boolean {
  const [result, setResult] = useState(false);

  useEffect(() => {
    const results = permissions.map(p => {
      const isAdmin = true; // TODO: 同上
      const userPermissions = isAdmin
        ? [...MOCK_USER_PERMISSIONS, 'logs:delete', 'logs:config']
        : MOCK_USER_PERMISSIONS;

      return (
        userPermissions.includes(p) ||
        userPermissions.includes('admin')
      );
    });

    setResult(mode === 'every' ? results.every(Boolean) : results.some(Boolean));
  }, [permissions, mode]);

  return result;
}

/**
 * 权限守卫组件
 * 当用户没有指定权限时显示替代内容
 */
interface PermissionGuardProps {
  permission: string;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export const PermissionGuard: React.FC<PermissionGuardProps> = ({
  permission,
  children,
  fallback,
}) => {
  const hasPermission = usePermission(permission);

  if (!hasPermission) {
    return <>{fallback || null}</>;
  }

  return <>{children}</>;
};

export default usePermission;
