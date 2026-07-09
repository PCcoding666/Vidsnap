import { createContext, useContext, useEffect } from 'react';
import type { ReactNode } from 'react';
import { apiClient } from '@/services/api';

// 登录已禁用：VidSnap slim 为"打开即用"，不接任何第三方身份系统（无登录墙）。
// 保留 AuthContext 形状，避免历史消费方（Header / HistoryPanel / ProtectedRoute 等）编译报错。
interface AuthUser {
  id: string;
  email?: string;
}

interface AuthContextType {
  user: AuthUser | null;
  session: null;
  isLoading: boolean;
  signOut: () => Promise<void>;
}

const stubValue: AuthContextType = {
  user: null,
  session: null,
  isLoading: false,
  // 登录已禁用：signOut 只需清掉任何残留 token（localStorage + ApiClient 内存态）
  signOut: async () => {
    apiClient.clearToken();
  },
};

const AuthContext = createContext<AuthContextType>(stubValue);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  // 登录禁用下清掉历史残留 token，避免 ApiClient 从 localStorage 读到旧 access_token
  // 后带着过期/错误的 Authorization 头请求（导致 401 或"伪登录"）。
  useEffect(() => {
    apiClient.clearToken();
  }, []);
  return <AuthContext.Provider value={stubValue}>{children}</AuthContext.Provider>;
};
