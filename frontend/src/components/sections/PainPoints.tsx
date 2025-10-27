import { motion } from 'framer-motion';

const painPoints = [
  {
    icon: '⏱️',
    title: '时间浪费',
    description: '2小时的视频课程，只想找那5分钟的核心内容',
    target: '学习者、职场人士',
  },
  {
    icon: '🔍',
    title: '内容难查找',
    description: '看完就忘，想回顾但找不到关键时间点',
    target: '内容创作者、研究人员',
  },
  {
    icon: '🌍',
    title: '语言障碍',
    description: '多语言视频听不懂，字幕翻译又不准确',
    target: '国际化用户',
  },
  {
    icon: '📝',
    title: '引用困难',
    description: '需要引用视频内容，但无法快速定位原话',
    target: '研究人员、写作者',
  },
];

export default function PainPoints() {
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
            你是否遇到这些问题？
          </h2>
          <p className="text-xl text-gray-600">
            我们理解你的痛苦，让我们来帮你解决
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {painPoints.map((point, index) => (
            <motion.div
              key={index}
              className="bg-white rounded-2xl p-8 shadow-lg hover:shadow-xl transition-all hover-lift"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
            >
              <div className="flex items-start space-x-4">
                <div className="text-5xl">{point.icon}</div>
                <div className="flex-1">
                  <h3 className="text-2xl font-bold text-gray-900 mb-3">
                    {point.title}
                  </h3>
                  <p className="text-gray-600 mb-3 text-lg">
                    {point.description}
                  </p>
                  <p className="text-sm text-primary-600 font-medium">
                    👥 {point.target}
                  </p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
