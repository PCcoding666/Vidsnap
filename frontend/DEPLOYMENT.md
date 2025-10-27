# 前端部署指南

## 部署方式

### 1. Vercel 部署 (推荐)

#### 步骤:

1. 安装 Vercel CLI:
```bash
npm install -g vercel
```

2. 登录 Vercel:
```bash
vercel login
```

3. 部署:
```bash
cd frontend
vercel deploy --prod
```

#### 配置环境变量:

在 Vercel 项目设置中添加:
- `VITE_API_BASE_URL`: 后端 API 地址
- `VITE_GRADIO_URL`: Gradio 应用地址

---

### 2. 阿里云 OSS + CDN 部署

#### 步骤:

1. 构建项目:
```bash
cd frontend
npm run build
```

2. 上传到 OSS:
```bash
# 使用阿里云 CLI 或 OSS 控制台上传 dist/ 目录
# 示例:
ossutil cp -r dist/ oss://your-bucket/frontend/
```

3. 配置 CDN:
- 在阿里云 CDN 控制台配置加速域名
- 指向 OSS 存储空间
- 设置 HTTPS 证书

4. 配置 index.html 为默认首页

---

### 3. Nginx 静态部署

#### Nginx 配置示例:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    root /var/www/frontend/dist;
    index index.html;
    
    # SPA 路由支持
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|svg|ico)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
```

#### 部署步骤:

1. 构建项目:
```bash
npm run build
```

2. 上传到服务器:
```bash
scp -r dist/ user@your-server:/var/www/frontend/
```

3. 重启 Nginx:
```bash
sudo systemctl restart nginx
```

---

## 构建优化

### 生产环境构建配置

在 `vite.config.ts` 中添加优化选项:

```typescript
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
          'animation': ['framer-motion'],
        },
      },
    },
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
  },
})
```

### 图片优化

- 使用 WebP 格式
- 配置响应式图片 (srcset)
- 启用懒加载

---

## 环境变量管理

### 开发环境 (.env.development)

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_GRADIO_URL=http://localhost:7860
```

### 生产环境 (.env.production)

```env
VITE_API_BASE_URL=https://api.your-domain.com
VITE_GRADIO_URL=https://gradio.your-domain.com
```

---

## 监控与分析

### Google Analytics

在 `index.html` 中添加:

```html
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=GA_MEASUREMENT_ID"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'GA_MEASUREMENT_ID');
</script>
```

### Sentry 错误监控

```bash
npm install @sentry/react
```

在 `main.tsx` 中配置:

```typescript
import * as Sentry from "@sentry/react";

Sentry.init({
  dsn: "YOUR_SENTRY_DSN",
  integrations: [new Sentry.BrowserTracing()],
  tracesSampleRate: 1.0,
});
```

---

## 性能优化清单

- [x] 代码分割 (动态 import)
- [x] Tree-shaking (Vite 自动处理)
- [x] CSS 压缩
- [x] JS 压缩
- [ ] 图片懒加载
- [ ] 字体优化 (font-display: swap)
- [ ] Service Worker (PWA)
- [ ] CDN 加速
- [ ] Gzip/Brotli 压缩

---

## 安全配置

### CSP (Content Security Policy)

在 Nginx 中添加:

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' https://api.your-domain.com;";
```

### HTTPS 强制

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

---

## CI/CD 自动化部署

### GitHub Actions 示例

创建 `.github/workflows/deploy.yml`:

```yaml
name: Deploy Frontend

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Node.js
        uses: actions/setup-node@v2
        with:
          node-version: '18'
      
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Build
        run: |
          cd frontend
          npm run build
        env:
          VITE_API_BASE_URL: ${{ secrets.API_BASE_URL }}
          VITE_GRADIO_URL: ${{ secrets.GRADIO_URL }}
      
      - name: Deploy to Vercel
        uses: amondnet/vercel-action@v20
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.ORG_ID }}
          vercel-project-id: ${{ secrets.PROJECT_ID }}
          working-directory: ./frontend
```

---

## 故障排查

### 常见问题

1. **样式不生效**
   - 检查 Tailwind CSS 配置
   - 确认 PostCSS 插件安装

2. **路由 404**
   - 配置服务器支持 SPA 路由
   - 检查 `try_files` 配置

3. **环境变量未生效**
   - 确认变量以 `VITE_` 开头
   - 重新构建项目

4. **构建失败**
   - 检查 TypeScript 类型错误
   - 确认所有依赖已安装

---

## 联系支持

如有部署问题，请联系开发团队。
