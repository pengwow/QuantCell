import { Navigate } from 'react-router-dom';

const isAuthenticated = (): boolean => {
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
