import { useState } from 'react';
import { motion } from 'framer-motion';

export default function HeroSection() {
  const [inputValue, setInputValue] = useState('');
  const [inputMode, setInputMode] = useState<'url' | 'file'>('url');
  const [isProcessing, setIsProcessing] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;
    
    setIsProcessing(true);
    // TODO: 集成后端 API
    setTimeout(() => {
      setIsProcessing(false);
      alert('视频处理功能即将上线!');
    }, 2000);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setInputValue(file.name);
      // TODO: 处理文件上传
    }
  };

  return (
    <section 
      id="hero" 
      className="relative min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-white to-accent-purple/10 pt-16"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="text-center">
          {/* 主标题 */}
          <motion.h1
            className="text-5xl md:text-6xl lg:text-7xl font-bold mb-6"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <span className="text-gradient">
              Chat with Any Video,
            </span>
            <br />
            <span className="text-gray-900">
              Understand Everything
            </span>
          </motion.h1>

          {/* 副标题 */}
          <motion.p
            className="text-xl md:text-2xl text-gray-600 mb-8 max-w-3xl mx-auto"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            将任何视频变成可对话的知识库
            <br className="hidden md:block" />
            不再错过视频中的任何细节和灵感
          </motion.p>

          {/* 输入区域 */}
          <motion.div
            className="max-w-2xl mx-auto mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4 }}
          >
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* 模式切换 */}
              <div className="flex justify-center space-x-4 mb-4">
                <button
                  type="button"
                  onClick={() => setInputMode('url')}
                  className={`px-4 py-2 rounded-lg font-medium transition-all ${
                    inputMode === 'url'
                      ? 'bg-primary-500 text-white'
                      : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                  }`}
                >
                  📎 YouTube URL
                </button>
                <button
                  type="button"
                  onClick={() => setInputMode('file')}
                  className={`px-4 py-2 rounded-lg font-medium transition-all ${
                    inputMode === 'file'
                      ? 'bg-primary-500 text-white'
                      : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                  }`}
                >
                  📁 本地上传
                </button>
              </div>

              {/* 输入框 */}
              {inputMode === 'url' ? (
                <div className="relative">
                  <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder="粘贴 YouTube 链接，例如: https://youtube.com/watch?v=..."
                    className="w-full px-6 py-4 text-lg rounded-xl border-2 border-gray-300 focus:border-primary-500 focus:outline-none transition-colors"
                  />
                </div>
              ) : (
                <div className="relative border-2 border-dashed border-gray-300 rounded-xl p-8 hover:border-primary-500 transition-colors cursor-pointer">
                  <input
                    type="file"
                    accept="video/mp4,video/avi,video/mov,video/mkv"
                    onChange={handleFileUpload}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  />
                  <div className="text-center">
                    <div className="text-4xl mb-2">📤</div>
                    <p className="text-gray-600">
                      {inputValue || '点击或拖拽视频文件到这里'}
                    </p>
                    <p className="text-sm text-gray-400 mt-2">
                      支持 MP4, AVI, MOV, MKV 格式
                    </p>
                  </div>
                </div>
              )}

              {/* 提交按钮 */}
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <button
                  type="submit"
                  disabled={isProcessing}
                  className="bg-accent-orange hover:bg-accent-orange/90 text-white px-8 py-4 rounded-xl font-bold text-lg transition-all hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isProcessing ? '🔄 处理中...' : '🚀 免费开始分析'}
                </button>
                <button
                  type="button"
                  className="bg-white border-2 border-gray-300 hover:border-primary-500 text-gray-700 px-8 py-4 rounded-xl font-bold text-lg transition-all"
                >
                  📺 观看演示(1分钟)
                </button>
              </div>
            </form>
          </motion.div>

          {/* 信任数据 */}
          <motion.p
            className="text-sm text-gray-500"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.6 }}
          >
            已帮助 <span className="font-bold text-primary-600">2,847</span> 位用户节省{' '}
            <span className="font-bold text-primary-600">18,392</span> 小时观看时间
          </motion.p>
        </div>
      </div>

      {/* 背景装饰 */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-20 left-10 w-72 h-72 bg-primary-300/30 rounded-full blur-3xl"></div>
        <div className="absolute bottom-20 right-10 w-96 h-96 bg-accent-purple/20 rounded-full blur-3xl"></div>
      </div>
    </section>
  );
}
