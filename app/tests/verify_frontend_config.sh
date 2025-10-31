#!/bin/bash
# 前端 Supabase 配置验证脚本

set -e

echo "========================================"
echo "前端 Supabase 集成配置验证"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查项计数
CHECKS_PASSED=0
CHECKS_FAILED=0

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "📁 项目根目录: $PROJECT_ROOT"
echo "📁 前端目录: $FRONTEND_DIR"
echo ""

# 检查 1: 前端目录存在
echo "🔍 检查 1: 前端目录存在"
if [ -d "$FRONTEND_DIR" ]; then
    echo -e "${GREEN}✅ 前端目录存在${NC}"
    ((CHECKS_PASSED++))
else
    echo -e "${RED}❌ 前端目录不存在${NC}"
    ((CHECKS_FAILED++))
    exit 1
fi
echo ""

# 检查 2: .env.local 文件存在
echo "🔍 检查 2: .env.local 文件存在"
if [ -f "$FRONTEND_DIR/.env.local" ]; then
    echo -e "${GREEN}✅ .env.local 文件存在${NC}"
    ((CHECKS_PASSED++))
else
    echo -e "${RED}❌ .env.local 文件不存在${NC}"
    ((CHECKS_FAILED++))
fi
echo ""

# 检查 3: .gitignore 包含 *.local
echo "🔍 检查 3: .gitignore 包含 *.local 规则"
if [ -f "$FRONTEND_DIR/.gitignore" ] && grep -q "*.local" "$FRONTEND_DIR/.gitignore"; then
    echo -e "${GREEN}✅ .gitignore 包含 *.local 规则${NC}"
    ((CHECKS_PASSED++))
else
    echo -e "${YELLOW}⚠️  .gitignore 可能不包含 *.local 规则${NC}"
fi
echo ""

# 检查 4: .env.local 包含必需变量
echo "🔍 检查 4: .env.local 包含必需的环境变量"
if [ -f "$FRONTEND_DIR/.env.local" ]; then
    MISSING_VARS=()
    
    if ! grep -q "VITE_SUPABASE_URL" "$FRONTEND_DIR/.env.local"; then
        MISSING_VARS+=("VITE_SUPABASE_URL")
    fi
    
    if ! grep -q "VITE_SUPABASE_ANON_KEY" "$FRONTEND_DIR/.env.local"; then
        MISSING_VARS+=("VITE_SUPABASE_ANON_KEY")
    fi
    
    if ! grep -q "VITE_BACKEND_API_URL" "$FRONTEND_DIR/.env.local"; then
        MISSING_VARS+=("VITE_BACKEND_API_URL")
    fi
    
    if [ ${#MISSING_VARS[@]} -eq 0 ]; then
        echo -e "${GREEN}✅ 所有必需变量都已配置${NC}"
        ((CHECKS_PASSED++))
    else
        echo -e "${RED}❌ 缺少以下变量: ${MISSING_VARS[*]}${NC}"
        ((CHECKS_FAILED++))
    fi
fi
echo ""

# 检查 5: node_modules 目录存在
echo "🔍 检查 5: node_modules 目录存在（依赖已安装）"
if [ -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${GREEN}✅ node_modules 目录存在，依赖已安装${NC}"
    ((CHECKS_PASSED++))
else
    echo -e "${YELLOW}⚠️  node_modules 目录不存在，请运行: cd frontend && npm install${NC}"
fi
echo ""

# 检查 6: 读取并显示配置值
echo "🔍 检查 6: 配置值预览"
if [ -f "$FRONTEND_DIR/.env.local" ]; then
    echo "--- .env.local 配置 ---"
    
    # 提取 URL（脱敏显示）
    SUPABASE_URL=$(grep "VITE_SUPABASE_URL" "$FRONTEND_DIR/.env.local" | cut -d'=' -f2)
    if [ -n "$SUPABASE_URL" ]; then
        echo -e "VITE_SUPABASE_URL: ${GREEN}${SUPABASE_URL}${NC}"
    else
        echo -e "VITE_SUPABASE_URL: ${RED}未配置${NC}"
    fi
    
    # 提取 ANON_KEY（脱敏显示）
    ANON_KEY=$(grep "VITE_SUPABASE_ANON_KEY" "$FRONTEND_DIR/.env.local" | cut -d'=' -f2)
    if [ -n "$ANON_KEY" ]; then
        ANON_KEY_PREVIEW="${ANON_KEY:0:30}...${ANON_KEY: -10}"
        echo -e "VITE_SUPABASE_ANON_KEY: ${GREEN}${ANON_KEY_PREVIEW}${NC}"
    else
        echo -e "VITE_SUPABASE_ANON_KEY: ${RED}未配置${NC}"
    fi
    
    # 提取后端 API URL
    BACKEND_URL=$(grep "VITE_BACKEND_API_URL" "$FRONTEND_DIR/.env.local" | cut -d'=' -f2)
    if [ -n "$BACKEND_URL" ]; then
        echo -e "VITE_BACKEND_API_URL: ${GREEN}${BACKEND_URL}${NC}"
    else
        echo -e "VITE_BACKEND_API_URL: ${RED}未配置${NC}"
    fi
    
    ((CHECKS_PASSED++))
fi
echo ""

# 检查 7: 对比后端配置（如果存在）
echo "🔍 检查 7: 前后端配置一致性"
BACKEND_ENV="$PROJECT_ROOT/.env"
if [ -f "$BACKEND_ENV" ] && [ -f "$FRONTEND_DIR/.env.local" ]; then
    BACKEND_URL=$(grep "^SUPABASE_URL" "$BACKEND_ENV" | cut -d'=' -f2)
    FRONTEND_URL=$(grep "VITE_SUPABASE_URL" "$FRONTEND_DIR/.env.local" | cut -d'=' -f2)
    
    if [ "$BACKEND_URL" == "$FRONTEND_URL" ]; then
        echo -e "${GREEN}✅ 前后端 Supabase URL 一致${NC}"
        ((CHECKS_PASSED++))
    else
        echo -e "${RED}❌ 前后端 Supabase URL 不一致${NC}"
        echo "   后端: $BACKEND_URL"
        echo "   前端: $FRONTEND_URL"
        ((CHECKS_FAILED++))
    fi
else
    echo -e "${YELLOW}⚠️  无法对比（后端 .env 文件不存在）${NC}"
fi
echo ""

# 总结
echo "========================================"
echo "验证总结"
echo "========================================"
echo -e "✅ 通过: ${GREEN}${CHECKS_PASSED}${NC}"
echo -e "❌ 失败: ${RED}${CHECKS_FAILED}${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 所有配置验证通过！${NC}"
    echo ""
    echo "下一步："
    echo "1. 启动前端开发服务器: cd frontend && npm run dev"
    echo "2. 访问 http://localhost:8080"
    echo "3. 在浏览器控制台验证 Supabase 连接"
    exit 0
else
    echo -e "${RED}⚠️  存在配置问题，请检查上述失败项${NC}"
    exit 1
fi
