#!/bin/bash
# 前后端集成测试脚本

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  前后端集成测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 测试结果统计
PASSED=0
FAILED=0

# 测试函数
test_case() {
    local name="$1"
    local command="$2"
    
    echo -e "${YELLOW}测试: $name${NC}"
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 通过${NC}"
        ((PASSED++))
    else
        echo -e "${RED}❌ 失败${NC}"
        ((FAILED++))
    fi
    echo ""
}

# 等待服务启动
wait_for_service() {
    local url="$1"
    local service_name="$2"
    local max_wait=30
    local count=0
    
    echo -e "${BLUE}等待 $service_name 启动...${NC}"
    
    while [ $count -lt $max_wait ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ $service_name 已就绪${NC}"
            return 0
        fi
        sleep 1
        ((count++))
        echo -n "."
    done
    
    echo ""
    echo -e "${RED}❌ $service_name 启动超时${NC}"
    return 1
}

# 步骤 1: 检查服务是否运行
echo -e "${BLUE}步骤 1: 检查服务状态${NC}"
echo ""

echo "检查后端服务 (FastAPI)..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 后端服务运行中${NC}"
else
    echo -e "${YELLOW}⚠️  后端服务未运行，请在另一个终端运行:${NC}"
    echo "   ./start_backend.sh api"
    echo ""
    read -p "按 Enter 继续（确认已启动后端）..."
fi

echo ""
echo "检查前端服务 (React)..."
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 前端服务运行中${NC}"
else
    echo -e "${YELLOW}⚠️  前端服务未运行，请在另一个终端运行:${NC}"
    echo "   cd frontend && npm run dev"
    echo ""
    read -p "按 Enter 继续（确认已启动前端）..."
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 2: 后端 API 测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 测试健康检查
test_case "健康检查" \
    "curl -s http://localhost:8000/health | grep -q 'healthy'"

# 测试服务状态
test_case "服务状态" \
    "curl -s http://localhost:8000/video/status | grep -q 'success'"

# 测试 API 文档
test_case "API 文档可访问" \
    "curl -s http://localhost:8000/docs | grep -q 'Swagger'"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 3: 跨域配置测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 测试 CORS 头
echo "检查 CORS 配置..."
CORS_HEADERS=$(curl -s -I http://localhost:8000/health | grep -i "access-control")
if [ -n "$CORS_HEADERS" ]; then
    echo -e "${GREEN}✅ CORS 配置正确${NC}"
    echo "$CORS_HEADERS"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  未检测到 CORS 头（可能需要实际跨域请求触发）${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 4: 前端资源加载测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 测试前端首页
test_case "前端首页可访问" \
    "curl -s http://localhost:8080 | grep -q 'root'"

# 测试前端资源
test_case "前端静态资源" \
    "curl -s -I http://localhost:8080/src/main.tsx | grep -q '200'"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 5: 前后端数据交互测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo "测试前端调用后端 API（通过代理）..."

# 创建临时测试脚本
cat > /tmp/test_api_call.js << 'JSEOF'
// 模拟前端调用后端
fetch('http://localhost:8080/api/health')
  .then(res => res.json())
  .then(data => {
    if (data.status === 'healthy') {
      console.log('SUCCESS');
      process.exit(0);
    } else {
      console.error('FAILED');
      process.exit(1);
    }
  })
  .catch(err => {
    console.error('ERROR:', err.message);
    process.exit(1);
  });
JSEOF

if command -v node &> /dev/null; then
    if timeout 5 node /tmp/test_api_call.js 2>&1 | grep -q "SUCCESS"; then
        echo -e "${GREEN}✅ 前端通过代理访问后端成功${NC}"
        ((PASSED++))
    else
        echo -e "${YELLOW}⚠️  代理测试失败（确保 Vite 代理配置正确）${NC}"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠️  未安装 Node.js，跳过 JS 测试${NC}"
fi

# 清理
rm -f /tmp/test_api_call.js

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 6: 用户认证流程测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 生成测试用户数据
TEST_EMAIL="integration_test_$(date +%s)@example.com"
TEST_PASSWORD="Test123456!"

echo "测试用户注册..."
SIGNUP_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")

if echo "$SIGNUP_RESPONSE" | grep -q "access_token"; then
    echo -e "${GREEN}✅ 用户注册成功${NC}"
    ((PASSED++))
    
    # 提取 token
    ACCESS_TOKEN=$(echo "$SIGNUP_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
    
    echo ""
    echo "测试用户登录..."
    SIGNIN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/signin \
      -H "Content-Type: application/json" \
      -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")
    
    if echo "$SIGNIN_RESPONSE" | grep -q "access_token"; then
        echo -e "${GREEN}✅ 用户登录成功${NC}"
        ((PASSED++))
    else
        echo -e "${RED}❌ 用户登录失败${NC}"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠️  用户注册失败（可能是 Supabase 未配置）${NC}"
    echo "响应: $SIGNUP_RESPONSE"
    ((FAILED++))
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}测试结果汇总${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo -e "${GREEN}✅ 通过: $PASSED${NC}"
echo -e "${RED}❌ 失败: $FAILED${NC}"

echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 所有测试通过！前后端集成正常${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  部分测试失败，请检查配置${NC}"
    exit 1
fi
