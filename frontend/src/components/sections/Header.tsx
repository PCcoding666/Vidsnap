import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

export default function Header() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [activeSection, setActiveSection] = useState('');

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 50);
      
      // 检测当前浏览区块
      const sections = ['hero', 'features', 'how-it-works', 'use-cases'];
      for (const section of sections) {
        const element = document.getElementById(section);
        if (element) {
          const rect = element.getBoundingClientRect();
          if (rect.top <= 100 && rect.bottom >= 100) {
            setActiveSection(section);
            break;
          }
        }
      }
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToSection = (sectionId: string) => {
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const navItems = [
    { id: 'features', label: '核心功能' },
    { id: 'how-it-works', label: '工作流程' },
    { id: 'use-cases', label: '使用场景' },
  ];

  return (
    <motion.header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled
          ? 'bg-white/80 backdrop-blur-md shadow-md'
          : 'bg-transparent'
      }`}
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div 
            className="flex items-center cursor-pointer"
            onClick={() => scrollToSection('hero')}
          >
            <div className="text-2xl font-bold text-gradient">
              🎬 VideoChat
            </div>
          </div>

          {/* 导航菜单 */}
          <nav className="hidden md:flex items-center space-x-8">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => scrollToSection(item.id)}
                className={`text-sm font-medium transition-colors ${
                  activeSection === item.id
                    ? 'text-primary-600'
                    : 'text-gray-600 hover:text-primary-500'
                }`}
              >
                {item.label}
              </button>
            ))}
            <a 
              href="#docs" 
              className="text-sm font-medium text-gray-600 hover:text-primary-500 transition-colors"
            >
              文档
            </a>
          </nav>

          {/* 右侧按钮 */}
          <div className="flex items-center space-x-4">
            <button className="hidden md:inline-flex text-sm font-medium text-gray-600 hover:text-primary-500 transition-colors">
              登录
            </button>
            <button className="bg-accent-orange hover:bg-accent-orange/90 text-white px-6 py-2 rounded-lg font-medium transition-all hover:shadow-lg">
              免费试用
            </button>
          </div>
        </div>
      </div>
    </motion.header>
  );
}
