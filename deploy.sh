#!/usr/bin/env bash
# VidSnap 服务器部署脚本（在 ECS 上执行）
# 前置：已 git clone 本仓库、已 cp .env.prod.example .env 并填好 .env、已装 Docker + Compose 插件。
set -euo pipefail

cd "$(dirname "$0")"

BRANCH="vidsnap_slim"
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> 拉取最新 ${BRANCH}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull origin "${BRANCH}"

if [ ! -f .env ]; then
  echo "!! 缺少 .env，请先 cp .env.prod.example .env 并填写后再运行" >&2
  exit 1
fi

echo "==> 构建并启动容器"
${COMPOSE} up -d --build

echo "==> 容器状态"
${COMPOSE} ps

PORT="$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || echo 8080)"
echo "==> 健康检查（容器内）"
sleep 5
curl -fsS "http://localhost:${PORT:-8080}/health" && echo " OK" || echo "（后端可能还在启动，稍后再试 /health）"

echo "==> 完成。访问： http://<ECS公网IP>:${PORT:-8080}"
