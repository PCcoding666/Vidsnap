import api from './api';

/**
 * 创建摘要
 * @param {Object} summaryData - 摘要数据
 * @returns {Promise}
 */
export const createSummary = async (summaryData) => {
  return await api.post('/summaries', summaryData);
};

/**
 * 获取所有摘要
 * @returns {Promise}
 */
export const getSummaries = async () => {
  return await api.get('/summaries');
};

/**
 * 获取摘要详情
 * @param {string} id - 摘要ID
 * @returns {Promise}
 */
export const getSummaryById = async (id) => {
  return await api.get(`/summaries/${id}`);
};

/**
 * 更新摘要
 * @param {string} id - 摘要ID
 * @param {Object} data - 要更新的数据
 * @returns {Promise}
 */
export const updateSummary = async (id, data) => {
  return await api.patch(`/summaries/${id}`, data);
};

/**
 * 删除摘要
 * @param {string} id - 摘要ID
 * @returns {Promise}
 */
export const deleteSummary = async (id) => {
  return await api.delete(`/summaries/${id}`);
}; 