import { motion } from 'framer-motion';

const steps = [
  {
    number: '①',
    icon: '📎',
    title: '粘贴链接',
    description: 'YouTube/本地视频\n一键上传',
    color: 'from-blue-400 to-blue-600',
  },
  {
    number: '②',
    icon: '🤖',
    title: 'AI分析',
    description: '自动提取音频\n智能转录字幕\n生成摘要结构',
    color: 'from-purple-400 to-purple-600',
  },
  {
    number: '③',
    icon: '💬',
    title: '开始对话',
    description: '随时提问\n精准回答\n深度挖掘',
    color: 'from-orange-400 to-orange-600',
  },
];

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="py-20 bg-gradient-to-br from-primary-50 to-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
            只需三步，开始智能对话
          </h2>
          <p className="text-xl text-gray-600">
            简单易用，无需专业知识
          </p>
        </motion.div>

        <div className="relative">
          {/* 流程步骤 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-4">
            {steps.map((step, index) => (
              <motion.div
                key={index}
                className="relative"
                initial={{ opacity: 0, x: -30 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: index * 0.2 }}
              >
                <div className="bg-white rounded-2xl p-8 shadow-xl hover:shadow-2xl transition-all hover-lift">
                  <div className="flex flex-col items-center text-center">
                    <div
                      className={`w-20 h-20 rounded-full bg-gradient-to-br ${step.color} flex items-center justify-center text-4xl mb-4 shadow-lg`}
                    >
                      {step.icon}
                    </div>
                    <div className="text-3xl font-bold text-primary-600 mb-2">
                      {step.number}
                    </div>
                    <h3 className="text-2xl font-bold text-gray-900 mb-3">
                      {step.title}
                    </h3>
                    <p className="text-gray-600 whitespace-pre-line">
                      {step.description}
                    </p>
                  </div>
                </div>

                {/* 连接箭头 (仅桌面端显示) */}
                {index < steps.length - 1 && (
                  <div className="hidden md:block absolute top-1/2 -right-6 transform -translate-y-1/2 z-10">
                    <div className="text-4xl text-primary-400 animate-pulse">
                      →
                    </div>
                  </div>
                )}
              </motion.div>
            ))}
          </div>

          {/* 性能指标 */}
          <motion.div
            className="mt-16 text-center"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.6 }}
          >
            <div className="inline-block bg-gradient-to-r from-accent-green to-emerald-600 text-white px-8 py-4 rounded-full shadow-lg">
              <p className="text-xl font-bold">
                ⏱️ 平均处理时间：5分钟视频 &lt; 30秒
              </p>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
