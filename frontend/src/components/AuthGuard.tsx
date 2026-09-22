import { Navigate } from 'react-router-dom';
import { desktopBypassAuth, isTauri } from '@/desktop/env';

const isAuthenticated = (): boolean => {
  // 桌面 local 模式：sidecar 由本应用自启并绑定 127.0.0.1，后端已豁免鉴权
  if (isTauri() && desktopBypassAuth()) return true;
  const token = localStorage.getItem('access_token');
  return !!token && token !== 'null' && token !== 'undefined';
};

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    sessionStorage.setItem('redirect_after_login', window.location.pathname);
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
