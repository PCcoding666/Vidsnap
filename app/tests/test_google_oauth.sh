#!/bin/bash
# Google OAuth 登录功能测试脚本

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
BACKEND_URL="http://localhost:8000"
REDIRECT_URL="http://localhost:5173/auth/callback"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Google OAuth 登录功能测试${NC}"
echo -e "${BLUE}========================================${NC}\n"

# 测试 1: 检查后端服务
echo -e "${YELLOW}[测试 1] 检查后端服务是否运行...${NC}"
if curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/docs" | grep -q "200"; then
    echo -e "${GREEN}✓ 后端服务运行正常${NC}\n"
else
    echo -e "${RED}✗ 后端服务未运行或不可访问${NC}"
    echo -e "${YELLOW}提示: 请先运行 'cd backend && uvicorn app.main:app --reload'${NC}\n"
    exit 1
fi

# 测试 2: 检查 Supabase 配置
echo -e "${YELLOW}[测试 2] 检查 Supabase 配置...${NC}"
python3 -c "from app.services.supabase_service import supabase_service; exit(0 if supabase_service.is_available() else 1)" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Supabase 服务配置正确${NC}\n"
else
    echo -e "${RED}✗ Supabase 服务不可用${NC}"
    echo -e "${YELLOW}提示: 请检查 .env 文件中的 SUPABASE_* 环境变量${NC}\n"
    exit 1
fi

# 测试 3: 获取 Google OAuth URL
echo -e "${YELLOW}[测试 3] 获取 Google OAuth URL...${NC}"
OAUTH_RESPONSE=$(curl -s "${BACKEND_URL}/auth/oauth/google?redirect_url=${REDIRECT_URL}")

# 检查响应
if echo "$OAUTH_RESPONSE" | grep -q '"url"'; then
    OAUTH_URL=$(echo "$OAUTH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['url'])" 2>/dev/null)
    if [ -n "$OAUTH_URL" ]; then
        echo -e "${GREEN}✓ 成功获取 OAuth URL${NC}"
        echo -e "${BLUE}OAuth URL:${NC} $OAUTH_URL\n"
        
        # 保存 URL 到临时文件
        echo "$OAUTH_URL" > /tmp/google_oauth_url.txt
        
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}✓ OAuth URL 生成成功!${NC}\n"
        echo -e "${BLUE}下一步操作:${NC}"
        echo -e "1. 在浏览器中打开上述 URL 进行 Google 登录"
        echo -e "2. 授权后会重定向到: ${REDIRECT_URL}?code=xxx"
        echo -e "3. 复制 URL 中的 code 参数"
        echo -e "4. 运行以下命令测试授权码交换:\n"
        echo -e "${YELLOW}curl -X POST \"${BACKEND_URL}/auth/oauth/callback\" \\${NC}"
        echo -e "${YELLOW}  -H \"Content-Type: application/json\" \\${NC}"
        echo -e "${YELLOW}  -d '{\"code\": \"YOUR_CODE_HERE\"}'${NC}\n"
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
        
        # 尝试在浏览器中打开(macOS)
        if command -v open &> /dev/null; then
            read -p "是否在浏览器中打开 OAuth URL? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                open "$OAUTH_URL"
                echo -e "${GREEN}✓ 已在浏览器中打开${NC}\n"
            fi
        fi
    else
        echo -e "${RED}✗ OAuth URL 为空${NC}\n"
        exit 1
    fi
else
    echo -e "${RED}✗ 获取 OAuth URL 失败${NC}"
    echo -e "${YELLOW}响应内容:${NC} $OAUTH_RESPONSE\n"
    exit 1
fi

# 测试 4: 交互式测试授权码交换
echo -e "${YELLOW}[测试 4] 交互式测试授权码交换${NC}"
read -p "已经获得授权码了吗? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "请输入授权码(code): " AUTH_CODE
    
    if [ -n "$AUTH_CODE" ]; then
        echo -e "${YELLOW}正在交换授权码...${NC}"
        TOKEN_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/auth/oauth/callback" \
            -H "Content-Type: application/json" \
            -d "{\"code\": \"$AUTH_CODE\"}")
        
        # 检查响应
        if echo "$TOKEN_RESPONSE" | grep -q '"access_token"'; then
            echo -e "${GREEN}✓ 授权码交换成功!${NC}\n"
            echo -e "${BLUE}用户信息:${NC}"
            echo "$TOKEN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$TOKEN_RESPONSE"
            
            # 提取 access_token
            ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
            
            if [ -n "$ACCESS_TOKEN" ]; then
                # 测试 Token 验证
                echo -e "\n${YELLOW}[测试 5] 验证 Access Token...${NC}"
                USER_INFO=$(curl -s -X GET "${BACKEND_URL}/auth/me" \
                    -H "Authorization: Bearer $ACCESS_TOKEN")
                
                if echo "$USER_INFO" | grep -q '"email"'; then
                    echo -e "${GREEN}✓ Token 验证成功!${NC}\n"
                    echo -e "${BLUE}当前用户信息:${NC}"
                    echo "$USER_INFO" | python3 -m json.tool 2>/dev/null || echo "$USER_INFO"
                    
                    echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                    echo -e "${GREEN}✓ 所有测试通过! Google OAuth 登录功能正常工作${NC}"
                    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
                else
                    echo -e "${RED}✗ Token 验证失败${NC}"
                    echo "$USER_INFO"
                fi
            fi
        else
            echo -e "${RED}✗ 授权码交换失败${NC}"
            echo -e "${YELLOW}响应内容:${NC} $TOKEN_RESPONSE\n"
        fi
    else
        echo -e "${YELLOW}跳过授权码交换测试${NC}\n"
    fi
else
    echo -e "${YELLOW}跳过授权码交换测试${NC}\n"
    echo -e "${BLUE}提示: 完成 Google 登录授权后,再次运行此脚本并选择 'y'${NC}\n"
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  测试完成${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${YELLOW}📚 更多信息请参阅:${NC}"
echo -e "  - Google OAuth 配置指南: backend/GOOGLE_OAUTH_SETUP_GUIDE.md"
echo -e "  - API 文档: ${BACKEND_URL}/docs\n"
