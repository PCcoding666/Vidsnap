import { useState } from 'react';
import { motion } from 'framer-motion';

export default function CTASection() {
  const [email, setEmail] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // TODO: 集成后端
    alert('感谢你的兴趣！我们会尽快联系你。');
  };

  return (
    <section className="py-20 bg-gradient-to-br from-primary-600 via-primary-500 to-accent-purple relative overflow-hidden">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <motion.div
          className="text-center text-white"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            🎯 准备好让视频为你所用了吗？
          </h2>
          <p className="text-xl md:text-2xl mb-8 opacity-90">
            从你的第一个视频开始改变学习方式
          </p>

          <form onSubmit={handleSubmit} className="max-w-xl mx-auto mb-8">
            <div className="flex flex-col sm:flex-row gap-4">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="输入你的邮箱，获取早鸟优惠..."
                className="flex-1 px-6 py-4 rounded-xl text-gray-900 text-lg focus:outline-none focus:ring-4 focus:ring-white/50"
                required
              />
              <button
                type="submit"
                className="bg-accent-orange hover:bg-accent-orange/90 text-white px-8 py-4 rounded-xl font-bold text-lg transition-all hover:shadow-2xl whitespace-nowrap"
              >
                🚀 免费开始使用
              </button>
            </div>
          </form>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 text-sm opacity-90">
            <div className="flex items-center">
              <span className="text-xl mr-2">✓</span>
              无需信用卡
            </div>
            <div className="flex items-center">
              <span className="text-xl mr-2">✓</span>
              每月10个免费视频
            </div>
            <div className="flex items-center">
              <span className="text-xl mr-2">✓</span>
              随时取消
            </div>
          </div>

          <div className="mt-8">
            <button className="text-white/80 hover:text-white transition-colors underline">
              📞 联系我们了解企业方案
            </button>
          </div>
        </motion.div>
      </div>

      {/* 背景装饰 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-white/10 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-accent-purple/30 rounded-full blur-3xl"></div>
      </div>
    </section>
  );
}
