import api from './api';

/**
 * 获取所有订阅计划
 * @returns {Promise}
 */
export const getSubscriptionPlans = async () => {
  return await api.get('/subscription/plans');
};

/**
 * 获取当前用户的订阅状态
 * @returns {Promise}
 */
export const getSubscriptionStatus = async () => {
  return await api.get('/subscription/status');
};

/**
 * 获取当前用户的订阅信息
 * @returns {Promise}
 */
export const getSubscription = async () => {
  return await api.get('/subscription');
};

/**
 * 创建新订阅
 * @param {Object} subscriptionData - 订阅数据
 * @returns {Promise}
 */
export const createSubscription = async (subscriptionData) => {
  return await api.post('/subscription', subscriptionData);
};

/**
 * 取消当前订阅
 * @returns {Promise}
 */
export const cancelSubscription = async () => {
  return await api.delete('/subscription');
}; 