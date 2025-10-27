# 前端主页 - YouTube 视频智能总结系统

这是 YouTube 视频智能总结系统的营销展示主页，采用现代化设计和流畅的动画效果。

## 🎯 项目特点

- ✨ 现代化设计，精美的 UI
- 🎬 流畅的动画效果 (Framer Motion)
- 📱 完全响应式设计
- ⚡ 基于 Vite 的快速开发体验
- 🎨 Tailwind CSS 样式系统
- 📦 TypeScript 类型安全

## 🚀 快速开始

### 安装依赖

```bash
npm install
```

### 开发模式运行

```bash
npm run dev
```

访问 http://localhost:5173 查看页面

### 构建生产版本

```bash
npm run build
```

### 预览生产版本

```bash
npm run preview
```

## 📁 项目结构

```
frontend/
├── src/
│   ├── components/
│   │   ├── sections/       # 页面区块组件
│   │   │   ├── Header.tsx
│   │   │   ├── HeroSection.tsx
│   │   │   ├── PainPoints.tsx
│   │   │   ├── Features.tsx
│   │   │   ├── HowItWorks.tsx
│   │   │   ├── UseCases.tsx
│   │   │   ├── CTASection.tsx
│   │   │   └── Footer.tsx
│   │   └── ui/             # 可复用 UI 组件
│   ├── App.tsx             # 主应用组件
│   ├── main.tsx            # 应用入口
│   └── index.css           # 全局样式
├── public/                 # 静态资源
├── index.html
├── package.json
├── tailwind.config.js      # Tailwind 配置
├── tsconfig.json           # TypeScript 配置
└── vite.config.ts          # Vite 配置
```

## 🎨 设计系统

### 颜色方案

- **主色调**: #6366F1 (靛蓝紫)
- **辅助色**: 
  - 翠绿: #10B981
  - 橙色: #F59E0B (CTA按钮)
  - 粉紫: #EC4899
  - 蓝色: #3B82F6
  - 紫色: #8B5CF6

### 字体

- 标题字体: Poppins / PingFang SC
- 正文字体: Inter / PingFang SC

## 🔧 环境变量配置

复制 `.env.example` 为 `.env` 并配置以下变量:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_GRADIO_URL=http://localhost:7860
```

## 📦 技术栈

- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **样式**: Tailwind CSS
- **动画**: Framer Motion
- **路由**: React Router (可选)

## 🌟 页面区块说明

1. **Header** - 固定导航栏,带滚动效果
2. **HeroSection** - 英雄区,主要价值主张 + CTA
3. **PainPoints** - 用户痛点展示
4. **Features** - 核心功能卡片
5. **HowItWorks** - 三步流程说明
6. **UseCases** - 用户角色和应用场景
7. **CTASection** - 最终行动号召
8. **Footer** - 页脚链接

## 🎯 待完成功能

- [ ] RealExample - 实际效果演示组件
- [ ] WhyUs - 技术优势展示
- [ ] SocialProof - 用户评价轮播
- [ ] 与后端 API 集成
- [ ] SEO 优化
- [ ] 性能优化(代码分割、懒加载)

## 📝 开发注意事项

- 所有组件均使用 Framer Motion 实现动画
- 响应式设计已集成在组件中
- 样式遵循 Tailwind CSS 最佳实践
- TypeScript 严格模式已启用

## 🚀 部署

### Vercel 部署 (推荐)

```bash
vercel deploy
```

### 阿里云 OSS 部署

```bash
npm run build
# 上传 dist/ 目录到 OSS
```

## 📄 License

MIT

---

**开发者**: Frontend Team  
**最后更新**: 2024
