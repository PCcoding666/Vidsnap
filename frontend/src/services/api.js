import axios from 'axios';

// API基础URL配置
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000/api/v1';

// 创建axios实例
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器：添加认证token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器：处理错误
api.interceptors.response.use(
  (response) => {
    // 为摘要API添加调试日志
    if (response.config.url.includes('/summaries')) {
      console.log('摘要API响应:', response.data);
    }
    return response.data;
  },
  (error) => {
    // API错误日志
    console.error('API错误:', error.response?.data || error.message);
    
    // 处理401未授权错误，清除token并重定向到登录页面
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    
    return Promise.reject(error);
  }
);

export default api; 