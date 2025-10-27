import { useState } from 'react';
import { motion } from 'framer-motion';

const exampleSummary = [
  { time: '0:00', title: '课程介绍', chapter: '第1章 机器学习概述' },
  { time: '3:15', title: '监督学习定义', chapter: '第2章 监督学习' },
  { time: '8:42', title: '回归问题示例', chapter: '第2章 监督学习' },
  { time: '15:20', title: '分类问题示例', chapter: '第3章 分类算法' },
  { time: '22:10', title: '无监督学习', chapter: '第4章 无监督学习' },
];

const exampleChat = [
  {
    question: '什么是监督学习?',
    answer: '在视频 3:24 处,教授解释:监督学习是指算法从带标签的训练数据中学习,目标是预测新数据的标签。例如,给定房屋面积预测价格就是典型的监督学习问题。',
    timestamp: '3:24',
  },
  {
    question: '监督学习和无监督学习的区别?',
    answer: '视频 22:35 讲到:主要区别在于数据是否有标签。监督学习使用带标签数据进行训练,而无监督学习从无标签数据中发现模式和结构,如聚类分析。',
    timestamp: '22:35',
  },
];

export default function RealExample() {
  const [activeTab, setActiveTab] = useState<'summary' | 'chat'>('summary');

  return (
    <section className="py-20 bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
            看看实际效果
          </h2>
          <p className="text-xl text-gray-600">
            以《斯坦福CS229机器学习第一课》为例
          </p>
        </motion.div>

        <motion.div
          className="bg-white rounded-2xl shadow-2xl overflow-hidden"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          {/* 视频预览区 */}
          <div className="relative bg-gray-900 aspect-video">
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center text-white">
                <div className="text-6xl mb-4">🎬</div>
                <p className="text-lg">视频播放器预览</p>
                <p className="text-sm text-gray-400 mt-2">1小时42分钟课程</p>
              </div>
            </div>
          </div>

          {/* 标签切换 */}
          <div className="border-b border-gray-200">
            <div className="flex">
              <button
                onClick={() => setActiveTab('summary')}
                className={`flex-1 px-6 py-4 text-center font-medium transition-colors ${
                  activeTab === 'summary'
                    ? 'border-b-2 border-primary-500 text-primary-600'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                📋 智能摘要
              </button>
              <button
                onClick={() => setActiveTab('chat')}
                className={`flex-1 px-6 py-4 text-center font-medium transition-colors ${
                  activeTab === 'chat'
                    ? 'border-b-2 border-primary-500 text-primary-600'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                💬 视频对话
              </button>
            </div>
          </div>

          {/* 内容区 */}
          <div className="p-6 md:p-8">
            {activeTab === 'summary' ? (
              <div className="space-y-4">
                <h3 className="text-xl font-bold text-gray-900 mb-4">
                  课程概要
                </h3>
                {exampleSummary.map((item, index) => (
                  <motion.div
                    key={index}
                    className="flex items-start space-x-4 p-4 rounded-lg hover:bg-gray-50 transition-colors cursor-pointer"
                    initial={{ opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.4, delay: index * 0.1 }}
                  >
                    <div className="flex-shrink-0 w-16 text-center">
                      <div className="bg-primary-100 text-primary-700 px-2 py-1 rounded font-mono text-sm">
                        {item.time}
                      </div>
                    </div>
                    <div className="flex-1">
                      <div className="text-sm text-gray-500 mb-1">
                        {item.chapter}
                      </div>
                      <div className="font-medium text-gray-900">
                        {item.title}
                      </div>
                    </div>
                    <div className="flex-shrink-0">
                      <button className="text-primary-600 hover:text-primary-700 text-sm">
                        跳转 →
                      </button>
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className="space-y-6">
                <h3 className="text-xl font-bold text-gray-900 mb-4">
                  智能问答示例
                </h3>
                {exampleChat.map((item, index) => (
                  <motion.div
                    key={index}
                    className="space-y-3"
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.4, delay: index * 0.15 }}
                  >
                    {/* 用户提问 */}
                    <div className="flex justify-end">
                      <div className="bg-primary-500 text-white px-4 py-3 rounded-2xl rounded-tr-sm max-w-md">
                        <p className="text-sm">{item.question}</p>
                      </div>
                    </div>
                    {/* AI 回答 */}
                    <div className="flex justify-start">
                      <div className="bg-gray-100 text-gray-900 px-4 py-3 rounded-2xl rounded-tl-sm max-w-2xl">
                        <p className="text-sm mb-2">{item.answer}</p>
                        <button className="text-xs text-primary-600 hover:text-primary-700 font-medium">
                          🎯 跳转到 {item.timestamp}
                        </button>
                      </div>
                    </div>
                  </motion.div>
                ))}
                <div className="pt-4 border-t border-gray-200">
                  <div className="flex items-center space-x-2">
                    <input
                      type="text"
                      placeholder="试试你的问题..."
                      className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-primary-500"
                    />
                    <button className="bg-primary-500 hover:bg-primary-600 text-white px-6 py-2 rounded-lg font-medium transition-colors">
                      发送
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* CTA 按钮 */}
          <div className="bg-gray-50 px-6 md:px-8 py-6 text-center border-t border-gray-200">
            <button className="bg-accent-orange hover:bg-accent-orange/90 text-white px-8 py-3 rounded-lg font-bold text-lg transition-all hover:shadow-lg">
              🚀 试试你自己的视频
            </button>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
