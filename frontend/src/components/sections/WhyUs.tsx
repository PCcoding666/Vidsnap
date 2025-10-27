import { motion } from 'framer-motion';

const advantages = [
  {
    icon: '🚀',
    title: '极速处理',
    points: ['30秒处理5分钟视频', '支持4K高清', '批量处理能力'],
    color: 'from-blue-500 to-blue-600',
  },
  {
    icon: '🎯',
    title: '精准理解',
    points: ['多模态AI理解', '上下文不丢失', '120+语言支持'],
    color: 'from-purple-500 to-purple-600',
  },
  {
    icon: '🔒',
    title: '安全可靠',
    points: ['隐私优先设计', '本地处理选项', '数据加密存储'],
    color: 'from-green-500 to-green-600',
  },
  {
    icon: '💰',
    title: '性价比高',
    points: ['免费额度慷慨', '按需付费', '无隐藏费用'],
    color: 'from-orange-500 to-orange-600',
  },
  {
    icon: '🔄',
    title: '灵活集成',
    points: ['支持多种视频源', 'API接入支持', 'Webhook 通知'],
    color: 'from-pink-500 to-pink-600',
  },
  {
    icon: '🌟',
    title: '稳定可靠',
    points: ['99.9%可用性', '24/7技术支持', 'SLA 保障'],
    color: 'from-indigo-500 to-indigo-600',
  },
];

export default function WhyUs() {
  return (
    <section className="py-20 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
            为什么选择我们?
          </h2>
          <p className="text-xl text-gray-600">
            专业、高效、可靠的视频智能分析服务
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {advantages.map((advantage, index) => (
            <motion.div
              key={index}
              className="bg-white rounded-2xl p-8 shadow-lg hover:shadow-2xl transition-all hover-lift border border-gray-100"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
            >
              <div className="flex flex-col items-center text-center">
                <div
                  className={`w-20 h-20 rounded-full bg-gradient-to-br ${advantage.color} flex items-center justify-center text-4xl mb-4 shadow-lg`}
                >
                  {advantage.icon}
                </div>
                <h3 className="text-2xl font-bold text-gray-900 mb-4">
                  {advantage.title}
                </h3>
                <ul className="space-y-3 w-full">
                  {advantage.points.map((point, pointIndex) => (
                    <li
                      key={pointIndex}
                      className="flex items-start text-gray-700"
                    >
                      <span className="text-primary-500 mr-2 mt-1">✓</span>
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </motion.div>
          ))}
        </div>

        {/* 性能对比 */}
        <motion.div
          className="mt-16 bg-gradient-to-br from-primary-50 to-purple-50 rounded-2xl p-8 md:p-12"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.6 }}
        >
          <h3 className="text-2xl md:text-3xl font-bold text-center text-gray-900 mb-8">
            性能对比
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center">
            <div>
              <div className="text-4xl md:text-5xl font-bold text-primary-600 mb-2">
                10x
              </div>
              <div className="text-gray-600">
                比手动整理<br />快10倍
              </div>
            </div>
            <div>
              <div className="text-4xl md:text-5xl font-bold text-accent-green mb-2">
                95%+
              </div>
              <div className="text-gray-600">
                转录准确率<br />行业领先
              </div>
            </div>
            <div>
              <div className="text-4xl md:text-5xl font-bold text-accent-orange mb-2">
                30s
              </div>
              <div className="text-gray-600">
                5分钟视频<br />处理时间
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
