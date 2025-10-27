import { motion } from 'framer-motion';

const features = [
  {
    icon: '🎯',
    title: '智能摘要',
    description: '一键生成多层次摘要',
    subFeatures: ['3秒概览', '章节拆解', '关键帧提取'],
    color: 'from-primary-400 to-primary-600',
  },
  {
    icon: '💬',
    title: '视频对话',
    description: '像和朋友聊天一样提问视频',
    subFeatures: ['多轮对话', '上下文理解', '追问深挖'],
    color: 'from-accent-purple to-accent-pink',
  },
  {
    icon: '🔍',
    title: '精准搜索',
    description: '找到视频中任何细节',
    subFeatures: ['语义搜索', '时间戳定位', '引用原文'],
    color: 'from-accent-blue to-primary-500',
  },
  {
    icon: '🌍',
    title: '多语言支持',
    description: '120+语言自动识别翻译',
    subFeatures: ['自动识别', '实时翻译', '双语字幕'],
    color: 'from-accent-green to-emerald-600',
  },
  {
    icon: '📊',
    title: '知识图谱',
    description: '可视化内容关系结构',
    subFeatures: ['主题提取', '关系图谱', '知识节点'],
    color: 'from-accent-orange to-red-500',
  },
  {
    icon: '📥',
    title: '一键导出',
    description: '多种格式一键分享',
    subFeatures: ['Markdown', 'PDF', 'JSON API'],
    color: 'from-purple-500 to-pink-600',
  },
];

export default function Features() {
  return (
    <section id="features" className="py-20 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
            强大的功能，简单的体验
          </h2>
          <p className="text-xl text-gray-600">
            一站式解决你的视频内容分析需求
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, index) => (
            <motion.div
              key={index}
              className="bg-white rounded-2xl p-8 shadow-lg hover:shadow-2xl transition-all hover-lift border border-gray-100"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              whileHover={{ scale: 1.02 }}
            >
              <div
                className={`w-16 h-16 rounded-xl bg-gradient-to-br ${feature.color} flex items-center justify-center text-3xl mb-4 shadow-lg`}
              >
                {feature.icon}
              </div>
              <h3 className="text-2xl font-bold text-gray-900 mb-2">
                {feature.title}
              </h3>
              <p className="text-gray-600 mb-4">{feature.description}</p>
              <ul className="space-y-2">
                {feature.subFeatures.map((subFeature, subIndex) => (
                  <li
                    key={subIndex}
                    className="flex items-center text-sm text-gray-700"
                  >
                    <span className="text-primary-500 mr-2">✓</span>
                    {subFeature}
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
