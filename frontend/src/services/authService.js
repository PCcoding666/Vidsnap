import api from './api';

/**
 * 用户注册
 * @param {Object} userData - 用户数据 (email, username, password)
 * @returns {Promise}
 */
export const register = async (userData) => {
  return await api.post('/auth/register', userData);
};

/**
 * 用户登录
 * @param {string} email - 邮箱
 * @param {string} password - 密码
 * @returns {Promise}
 */
export const login = async (email, password) => {
  // API使用表单格式提交
  const formData = new FormData();
  formData.append('username', email); // OAuth2 使用 username 参数，但实际上是邮箱
  formData.append('password', password);
  
  // 使用axios直接调用，因为需要特殊的content-type
  const response = await api.post('/auth/login', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });
  
  return response;
};

/**
 * 获取当前用户信息
 * @returns {Promise}
 */
export const getUser = async () => {
  return await api.get('/auth/me');
}; 