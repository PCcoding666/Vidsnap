import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const testimonials = [
  {
    name: '张同学',
    role: '产品经理',
    avatar: '👨‍💼',
    content: '终于不用看2小时废话了，直接定位到我需要的部分，节省了大量时间！工作效率提升明显。',
    rating: 5,
  },
  {
    name: '李经理',
    role: '创业者',
    avatar: '👔',
    content: '会议录音秒变行动清单，团队协作效率提升明显。每周能节省至少5小时的整理时间。',
    rating: 5,
  },
  {
    name: '王研究员',
    role: '博士生',
    avatar: '👨‍🔬',
    content: '学习效率提升3倍，文献视频分析从此不再痛苦。多语言支持特别好用！',
    rating: 5,
  },
  {
    name: '陈老师',
    role: '在线教育',
    avatar: '👨‍🏫',
    content: '用来制作课程笔记和重点标注，学生反馈非常好。AI总结质量超出预期。',
    rating: 5,
  },
  {
    name: '刘设计师',
    role: 'UI设计师',
    avatar: '🎨',
    content: '收集灵感素材的好帮手，快速提取设计教程的关键点。再也不用反复拖进度条了。',
    rating: 5,
  },
];

export default function SocialProof() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isAutoPlay, setIsAutoPlay] = useState(true);

  useEffect(() => {
    if (!isAutoPlay) return;

    const timer = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % testimonials.length);
    }, 5000);

    return () => clearInterval(timer);
  }, [isAutoPlay]);

  const handlePrev = () => {
    setIsAutoPlay(false);
    setCurrentIndex((prev) => 
      prev === 0 ? testimonials.length - 1 : prev - 1
    );
  };

  const handleNext = () => {
    setIsAutoPlay(false);
    setCurrentIndex((prev) => (prev + 1) % testimonials.length);
  };

  return (
    <section className="py-20 bg-gradient-to-br from-gray-50 to-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
            用户怎么说
          </h2>
          <div className="flex items-center justify-center space-x-2 text-yellow-400 text-3xl mb-2">
            {'⭐'.repeat(5)}
          </div>
          <p className="text-xl text-gray-600">
            <span className="font-bold text-gray-900">4.9/5.0</span> 综合评分 · 
            <span className="font-bold text-gray-900"> 1,234</span> 条评价
          </p>
        </motion.div>

        {/* 评价轮播 */}
        <div className="relative max-w-4xl mx-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentIndex}
              initial={{ opacity: 0, x: 100 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -100 }}
              transition={{ duration: 0.3 }}
              className="bg-white rounded-2xl p-8 md:p-12 shadow-xl"
            >
              <div className="flex flex-col items-center text-center">
                {/* 用户头像 */}
                <div className="text-6xl mb-4">
                  {testimonials[currentIndex].avatar}
                </div>

                {/* 评分 */}
                <div className="flex items-center space-x-1 text-yellow-400 text-xl mb-4">
                  {'⭐'.repeat(testimonials[currentIndex].rating)}
                </div>

                {/* 评价内容 */}
                <p className="text-xl text-gray-700 mb-6 leading-relaxed">
                  "{testimonials[currentIndex].content}"
                </p>

                {/* 用户信息 */}
                <div>
                  <div className="font-bold text-gray-900 text-lg">
                    {testimonials[currentIndex].name}
                  </div>
                  <div className="text-gray-600">
                    {testimonials[currentIndex].role}
                  </div>
                </div>
              </div>
            </motion.div>
          </AnimatePresence>

          {/* 左右切换按钮 */}
          <button
            onClick={handlePrev}
            className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-4 md:-translate-x-12 bg-white hover:bg-gray-50 rounded-full p-3 shadow-lg transition-all hover:scale-110"
            aria-label="上一条评价"
          >
            <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            onClick={handleNext}
            className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-4 md:translate-x-12 bg-white hover:bg-gray-50 rounded-full p-3 shadow-lg transition-all hover:scale-110"
            aria-label="下一条评价"
          >
            <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>

          {/* 指示器 */}
          <div className="flex items-center justify-center space-x-2 mt-8">
            {testimonials.map((_, index) => (
              <button
                key={index}
                onClick={() => {
                  setIsAutoPlay(false);
                  setCurrentIndex(index);
                }}
                className={`h-2 rounded-full transition-all ${
                  index === currentIndex
                    ? 'w-8 bg-primary-600'
                    : 'w-2 bg-gray-300 hover:bg-gray-400'
                }`}
                aria-label={`跳转到第 ${index + 1} 条评价`}
              />
            ))}
          </div>
        </div>

        {/* 统计数据 */}
        <motion.div
          className="grid grid-cols-2 md:grid-cols-4 gap-8 mt-16"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.4 }}
        >
          <div className="text-center">
            <div className="text-3xl md:text-4xl font-bold text-primary-600 mb-2">
              2,847
            </div>
            <div className="text-gray-600">活跃用户</div>
          </div>
          <div className="text-center">
            <div className="text-3xl md:text-4xl font-bold text-accent-green mb-2">
              18,392
            </div>
            <div className="text-gray-600">节省小时数</div>
          </div>
          <div className="text-center">
            <div className="text-3xl md:text-4xl font-bold text-accent-orange mb-2">
              45,621
            </div>
            <div className="text-gray-600">处理视频数</div>
          </div>
          <div className="text-center">
            <div className="text-3xl md:text-4xl font-bold text-accent-purple mb-2">
              99.2%
            </div>
            <div className="text-gray-600">用户满意度</div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
