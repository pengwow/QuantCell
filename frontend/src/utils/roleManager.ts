/**
 * 角色和权限管理工具
 * 用于管理用户角色、权限检查和访客状态
 */

// 用户角色枚举
export enum UserRole {
  GUEST = "guest",
  USER = "user",
  ADMIN = "admin",
}

// 权限枚举
export enum Permission {
  // 系统配置权限
  CONFIG_READ = "config:read",
  CONFIG_WRITE = "config:write",

  // 用户管理权限
  USER_READ = "user:read",
  USER_WRITE = "user:write",

  // 策略管理权限
  STRATEGY_READ = "strategy:read",
  STRATEGY_WRITE = "strategy:write",

  // 指标管理权限
  INDICATOR_READ = "indicator:read",
  INDICATOR_WRITE = "indicator:write",

  // 回测权限
  BACKTEST_READ = "backtest:read",
  BACKTEST_WRITE = "backtest:write",

  // 数据管理权限
  DATA_READ = "data:read",
  DATA_WRITE = "data:write",

  // AI功能权限
  AI_READ = "ai:read",
  AI_WRITE = "ai:write",

  // 系统日志权限
  LOG_READ = "log:read",

  // 交易所配置权限
  EXCHANGE_READ = "exchange:read",
  EXCHANGE_WRITE = "exchange:write",
}

// 角色权限映射
const ROLE_PERMISSIONS: Record<UserRole, Set<Permission>> = {
  [UserRole.GUEST]: new Set([
    // 访客只读权限
    Permission.CONFIG_READ,
    Permission.STRATEGY_READ,
    Permission.INDICATOR_READ,
    Permission.BACKTEST_READ,
    Permission.DATA_READ,
    Permission.AI_READ,
    Permission.LOG_READ,
    Permission.EXCHANGE_READ,
  ]),
  [UserRole.USER]: new Set([
    // 普通用户拥有大部分读写权限
    Permission.CONFIG_READ,
    Permission.CONFIG_WRITE,
    Permission.USER_READ,
    Permission.USER_WRITE,
    Permission.STRATEGY_READ,
    Permission.STRATEGY_WRITE,
    Permission.INDICATOR_READ,
    Permission.INDICATOR_WRITE,
    Permission.BACKTEST_READ,
    Permission.BACKTEST_WRITE,
    Permission.DATA_READ,
    Permission.DATA_WRITE,
    Permission.AI_READ,
    Permission.AI_WRITE,
    Permission.LOG_READ,
    Permission.EXCHANGE_READ,
    Permission.EXCHANGE_WRITE,
  ]),
  [UserRole.ADMIN]: new Set([
    // 管理员拥有所有权限
    ...Object.values(Permission),
  ]),
};

/**
 * 获取当前用户角色
 * @returns UserRole 用户角色
 */
export const getCurrentUserRole = (): UserRole => {
  if (typeof window === "undefined") return UserRole.GUEST;
  const role = localStorage.getItem("user_role");
  if (role === UserRole.GUEST || role === UserRole.USER || role === UserRole.ADMIN) {
    return role;
  }
  return UserRole.GUEST;
};

/**
 * 检查当前用户是否为访客
 * @returns boolean 是否为访客
 */
export const isGuestUser = (): boolean => {
  if (typeof window === "undefined") return true;
  const isGuest = localStorage.getItem("is_guest");
  return isGuest === "true" || getCurrentUserRole() === UserRole.GUEST;
};

/**
 * 获取当前用户名
 * @returns string 用户名
 */
export const getCurrentUsername = (): string => {
  if (typeof window === "undefined") return "访客";
  return localStorage.getItem("username") || "访客";
};

/**
 * 检查用户是否有指定权限
 * @param permission 需要检查的权限
 * @returns boolean 是否有权限
 */
export const hasPermission = (permission: Permission): boolean => {
  const role = getCurrentUserRole();
  const permissions = ROLE_PERMISSIONS[role] || new Set();
  return permissions.has(permission);
};

/**
 * 检查用户是否有写入权限（用于快速判断）
 * @returns boolean 是否有写入权限
 */
export const hasWritePermission = (): boolean => {
  return !isGuestUser();
};

/**
 * 保存用户角色信息
 * @param role 用户角色
 * @param isGuest 是否为访客
 * @param username 用户名
 */
export const saveUserRoleInfo = (role: UserRole, isGuest: boolean, username: string): void => {
  if (typeof window === "undefined") return;
  localStorage.setItem("user_role", role);
  localStorage.setItem("is_guest", String(isGuest));
  localStorage.setItem("username", username);
};

/**
 * 清除用户角色信息（登出时调用）
 */
export const clearUserRoleInfo = (): void => {
  if (typeof window === "undefined") return;
  localStorage.removeItem("user_role");
  localStorage.removeItem("is_guest");
  localStorage.removeItem("username");
};

/**
 * 获取受限功能的提示信息
 * @returns string 提示信息
 */
export const getRestrictedFeatureMessage = (): string => {
  return "该功能仅对注册用户开放，请使用普通用户账号登录。";
};
