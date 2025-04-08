from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, List, Dict

from app.models.subscription import SubscriptionCreate, SubscriptionRead, SubscriptionReadDetailed
from app.models.user import UserInDB
from app.services.auth.user_service import get_current_user
from app.services.payment.subscription_service import get_subscription_by_user_id, create_subscription, process_payment, cancel_subscription, get_all_plans, check_subscription_status

router = APIRouter()

@router.get("/plans", response_model=List[Dict[str, Any]])
async def read_plans() -> Any:
    """
    获取所有订阅计划
    """
    plans = get_all_plans()
    return plans

@router.get("/status", response_model=Dict[str, Any])
async def read_subscription_status(
    current_user: UserInDB = Depends(get_current_user)
) -> Any:
    """
    获取当前用户的订阅状态
    """
    status = check_subscription_status(current_user)
    return status

@router.get("", response_model=SubscriptionRead)
async def read_subscription(
    current_user: UserInDB = Depends(get_current_user)
) -> Any:
    """
    获取当前用户的订阅信息
    """
    subscription = get_subscription_by_user_id(current_user.id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到有效的订阅"
        )
    return subscription

@router.post("", response_model=SubscriptionReadDetailed)
async def create_subscription_plan(
    *,
    subscription_in: SubscriptionCreate,
    current_user: UserInDB = Depends(get_current_user)
) -> Any:
    """
    创建新的订阅计划
    """
    # 创建订阅
    subscription = create_subscription(current_user.id, subscription_in)
    
    # 免费计划无需处理支付
    if subscription.plan == "free":
        return subscription
    
    # 处理支付（示例支付信息）
    payment_details = {
        "method": subscription_in.payment_method,
        "timestamp": subscription.created_at.isoformat(),
        "amount": 0,
        "currency": "USD"
    }
    
    # 根据计划设置金额
    if subscription.plan == "basic":
        payment_details["amount"] = 9.99
    elif subscription.plan == "premium":
        payment_details["amount"] = 29.99
    
    # 处理支付
    payment_result = process_payment(subscription.id, payment_details)
    
    if not payment_result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"支付处理失败: {payment_result.error_message}"
        )
    
    # 获取更新后的订阅
    updated_subscription = get_subscription_by_user_id(current_user.id)
    if not updated_subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到更新后的订阅"
        )
    
    return updated_subscription

@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_subscription_plan(
    current_user: UserInDB = Depends(get_current_user)
):
    """
    取消当前用户的订阅
    """
    result = cancel_subscription(current_user.id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到有效的订阅"
        ) 