from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import uuid

from app.models.subscription import SubscriptionCreate, SubscriptionInDB, SubscriptionRead, PaymentProcessing
from app.models.user import UserInDB
from app.services.storage.json_storage import JSONStorage
from app.core.config import settings
from app.services.auth.user_service import user_storage

# 创建订阅存储服务
subscription_storage = JSONStorage[SubscriptionInDB](settings.SUBSCRIPTIONS_DATA_FILE, SubscriptionInDB)

def get_subscription_by_user_id(user_id: str) -> Optional[SubscriptionInDB]:
    """根据用户ID获取订阅"""
    subscriptions = subscription_storage.get_by_field("user_id", user_id)
    # 获取最新的激活订阅
    active_subscriptions = [sub for sub in subscriptions if sub.is_active]
    return active_subscriptions[0] if active_subscriptions else None

def get_subscription_by_id(subscription_id: str) -> Optional[SubscriptionInDB]:
    """根据ID获取订阅"""
    return subscription_storage.get_by_id(subscription_id)

def create_subscription(user_id: str, subscription_create: SubscriptionCreate) -> SubscriptionInDB:
    """创建新订阅"""
    # 获取用户当前的订阅
    current_subscription = get_subscription_by_user_id(user_id)
    
    # 如果用户已有激活的订阅，将其设置为不活跃
    if current_subscription:
        current_subscription.is_active = False
        subscription_storage.update(current_subscription.id, current_subscription)
    
    # 创建新订阅
    # 设置订阅过期时间，默认为1个月后
    expires_at = datetime.utcnow() + timedelta(days=30)
    
    subscription_in_db = SubscriptionInDB(
        user_id=user_id,
        plan=subscription_create.plan,
        expires_at=expires_at
    )
    
    # 保存订阅
    created_subscription = subscription_storage.create(subscription_in_db)
    
    # 更新用户的订阅计划
    user = user_storage.get_by_id(user_id)
    if user:
        user.subscription_plan = subscription_create.plan
        user_storage.update(user_id, user)
    
    return created_subscription

def process_payment(subscription_id: str, payment_details: Dict[str, Any]) -> PaymentProcessing:
    """处理支付"""
    subscription = get_subscription_by_id(subscription_id)
    if not subscription:
        return PaymentProcessing(
            subscription_id=subscription_id,
            success=False,
            error_message="订阅不存在"
        )
    
    # 假设支付成功
    payment_id = str(uuid.uuid4())
    
    # 更新订阅信息
    subscription.payment_id = payment_id
    subscription.payment_status = "completed"
    subscription.payment_details = payment_details
    
    subscription_storage.update(subscription_id, subscription)
    
    return PaymentProcessing(
        subscription_id=subscription_id,
        success=True,
        payment_id=payment_id
    )

def cancel_subscription(user_id: str) -> bool:
    """取消订阅"""
    subscription = get_subscription_by_user_id(user_id)
    if not subscription:
        return False
    
    # 设置订阅为不活跃
    subscription.is_active = False
    subscription.updated_at = datetime.utcnow()
    
    subscription_storage.update(subscription.id, subscription)
    
    # 更新用户订阅计划为免费
    user = user_storage.get_by_id(user_id)
    if user:
        user.subscription_plan = "free"
        user_storage.update(user_id, user)
    
    return True

def get_all_plans() -> List[Dict[str, Any]]:
    """获取所有订阅计划"""
    plans = []
    for plan_id, plan_details in settings.SUBSCRIPTION_PLANS.items():
        plan_info = {
            "id": plan_id,
            **plan_details
        }
        plans.append(plan_info)
    
    return plans

def check_subscription_status(user: UserInDB) -> Dict[str, Any]:
    """检查用户订阅状态"""
    # 获取用户订阅
    subscription = get_subscription_by_user_id(user.id)
    
    # 获取计划详情
    plan_details = settings.SUBSCRIPTION_PLANS.get(user.subscription_plan, {})
    
    result = {
        "plan": user.subscription_plan,
        "plan_name": plan_details.get("name", "未知"),
        "videos_per_month": plan_details.get("videos_per_month", 0),
        "videos_processed": user.usage.get("videos_processed", 0),
        "features": plan_details.get("features", []),
        "subscription_active": False,
        "expires_at": None
    }
    
    if subscription and subscription.is_active:
        result["subscription_active"] = True
        result["expires_at"] = subscription.expires_at
    
    return result 