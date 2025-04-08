from fastapi import APIRouter

from app.api.api_v1.endpoints import auth, summaries, subscription

api_router = APIRouter()

# 添加认证相关的路由
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# 添加摘要相关的路由
api_router.include_router(summaries.router, prefix="/summaries", tags=["summaries"])

# 添加订阅相关的路由
api_router.include_router(subscription.router, prefix="/subscription", tags=["subscription"]) 