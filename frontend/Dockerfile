# VidSnap 前端镜像（多阶段：vite 构建 -> nginx 托管）
# --- 构建阶段 ---
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
# 同源部署：API 走相对路径 /api/v1，由 nginx 反代到 backend，
# 换公网 IP / 域名都无需重新构建前端。
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build

# --- 运行阶段 ---
FROM nginx:alpine
# 自定义站点配置（SPA + /api 反代 + 上传/SSE/WS）
COPY nginx.conf /etc/nginx/conf.d/default.conf
# 构建产物
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
