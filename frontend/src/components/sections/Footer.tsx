export default function Footer() {
  return (
    <footer className="bg-gray-900 text-gray-300 py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          {/* 品牌信息 */}
          <div className="col-span-1">
            <div className="text-2xl font-bold text-white mb-4">
              🎬 VideoChat
            </div>
            <p className="text-sm text-gray-400">
              让每个视频都能成为你的知识伙伴
            </p>
          </div>

          {/* 产品 */}
          <div>
            <h3 className="text-white font-semibold mb-4">产品</h3>
            <ul className="space-y-2 text-sm">
              <li><a href="#features" className="hover:text-primary-400 transition-colors">核心功能</a></li>
              <li><a href="#pricing" className="hover:text-primary-400 transition-colors">定价方案</a></li>
              <li><a href="#api" className="hover:text-primary-400 transition-colors">API 文档</a></li>
              <li><a href="#updates" className="hover:text-primary-400 transition-colors">更新日志</a></li>
            </ul>
          </div>

          {/* 资源 */}
          <div>
            <h3 className="text-white font-semibold mb-4">资源</h3>
            <ul className="space-y-2 text-sm">
              <li><a href="#docs" className="hover:text-primary-400 transition-colors">使用文档</a></li>
              <li><a href="#blog" className="hover:text-primary-400 transition-colors">博客</a></li>
              <li><a href="#tutorials" className="hover:text-primary-400 transition-colors">教程</a></li>
              <li><a href="#faq" className="hover:text-primary-400 transition-colors">常见问题</a></li>
            </ul>
          </div>

          {/* 公司 */}
          <div>
            <h3 className="text-white font-semibold mb-4">公司</h3>
            <ul className="space-y-2 text-sm">
              <li><a href="#about" className="hover:text-primary-400 transition-colors">关于我们</a></li>
              <li><a href="#contact" className="hover:text-primary-400 transition-colors">联系我们</a></li>
              <li><a href="#privacy" className="hover:text-primary-400 transition-colors">隐私政策</a></li>
              <li><a href="#terms" className="hover:text-primary-400 transition-colors">服务条款</a></li>
            </ul>
          </div>
        </div>

        {/* 版权信息 */}
        <div className="border-t border-gray-800 pt-8 flex flex-col md:flex-row justify-between items-center">
          <p className="text-sm text-gray-400">
            © 2024 VideoChat. All rights reserved.
          </p>
          <div className="flex space-x-6 mt-4 md:mt-0">
            <a href="#twitter" className="hover:text-primary-400 transition-colors">Twitter</a>
            <a href="#github" className="hover:text-primary-400 transition-colors">GitHub</a>
            <a href="#discord" className="hover:text-primary-400 transition-colors">Discord</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
