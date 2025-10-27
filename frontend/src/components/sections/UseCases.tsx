import { motion } from 'framer-motion';

const useCases = [
  {
    icon: '🎓',
    role: '学习者',
    slogan: '2小时课程，30秒抓核心',
    scenarios: ['课程笔记生成', '知识点复习', '考前速览'],
    color: 'from-blue-100 to-blue-50',
  },
  {
    icon: '👨‍💼',
    role: '内容创作者',
    slogan: '快速提取竞品视频亮点做选题',
    scenarios: ['灵感素材收集', '脚本参考提取', '趋势分析'],
    color: 'from-purple-100 to-purple-50',
  },
  {
    icon: '📊',
    role: '职场人士',
    slogan: '会议录像秒变行动要点清单',
    scenarios: ['会议纪要整理', '培训内容提炼', '演讲稿生成'],
    color: 'from-green-100 to-green-50',
  },
  {
    icon: '🔬',
    role: '研究人员',
    slogan: '文献视频批量分析不费力',
    scenarios: ['学术视频标注', '访谈内容分析', '数据引用定位'],
    color: 'from-orange-100 to-orange-50',
  },
];

export default function UseCases() {
  return (
    <section id="use-cases" className="py-20 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
            适用于多种场景
          </h2>
          <p className="text-xl text-gray-600">
            无论你是谁，都能从中受益
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {useCases.map((useCase, index) => (
            <motion.div
              key={index}
              className={`bg-gradient-to-br ${useCase.color} rounded-2xl p-8 shadow-lg hover:shadow-2xl transition-all hover-lift border border-gray-200`}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
            >
              <div className="flex flex-col items-center text-center">
                <div className="text-6xl mb-4">{useCase.icon}</div>
                <h3 className="text-2xl font-bold text-gray-900 mb-2">
                  {useCase.role}
                </h3>
                <p className="text-lg italic text-gray-700 mb-6 font-medium">
                  "{useCase.slogan}"
                </p>
                <ul className="space-y-3 w-full">
                  {useCase.scenarios.map((scenario, scenarioIndex) => (
                    <li
                      key={scenarioIndex}
                      className="flex items-center text-gray-800 bg-white/70 px-4 py-2 rounded-lg"
                    >
                      <span className="text-primary-500 mr-2 text-xl">✓</span>
                      <span>{scenario}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
