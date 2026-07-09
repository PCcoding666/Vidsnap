import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

// 登录已禁用（VidSnap slim 打开即用）。保留 /login 路由以兼容旧链接，直接回首页。
const Login = () => {
  const navigate = useNavigate();
  useEffect(() => {
    navigate('/', { replace: true });
  }, [navigate]);
  return null;
};

export default Login;
