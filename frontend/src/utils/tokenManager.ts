// JWT令牌管理工具
// 处理JWT令牌的存储、获取和刷新

/**
 * JWT令牌类型定义
 */
export interface JWTToken {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

/**
 * 令牌存储键名
 */
const TOKEN_STORAGE_KEY = 'quantcell_jwt_token';

/**
 * 存储JWT令牌
 * @param token 要存储的JWT令牌
 */
export const saveToken = (token: JWTToken): void => {
  localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(token));
};

/**
 * 获取存储的JWT令牌
 * @returns 存储的JWT令牌，或undefined
 */
export const getToken = (): JWTToken | undefined => {
  const tokenStr = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (tokenStr) {
    try {
      return JSON.parse(tokenStr);
    } catch (e) {
      console.error('解析令牌失败:', e);
      removeToken();
      return undefined;
    }
  }
  return undefined;
};

/**
 * 获取访问令牌
 * @returns 访问令牌字符串，或undefined
 */
export const getAccessToken = (): string | undefined => {
  const token = getToken();
  return token?.access_token;
};

/**
 * 获取刷新令牌
 * @returns 刷新令牌字符串，或undefined
 */
export const getRefreshToken = (): string | undefined => {
  const token = getToken();
  return token?.refresh_token;
};

/**
 * 删除存储的JWT令牌
 */
export const removeToken = (): void => {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
};

/**
 * 检查是否已登录（是否有有效的访问令牌）
 * @returns 是否已登录
 */
export const isLoggedIn = (): boolean => {
  return !!getAccessToken();
};

/**
 * 更新访问令牌
 * @param newAccessToken 新的访问令牌
 */
export const updateAccessToken = (newAccessToken: string): void => {
  const token = getToken();
  if (token) {
    token.access_token = newAccessToken;
    saveToken(token);
  }
};
