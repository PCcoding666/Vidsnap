import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';

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
  signOut: async () => {},
};

const AuthContext = createContext<AuthContextType>(stubValue);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  return <AuthContext.Provider value={stubValue}>{children}</AuthContext.Provider>;
};
