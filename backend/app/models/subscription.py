from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class SubscriptionBase(BaseModel):
    """订阅基本信息"""
    plan: str  # free, basic, premium

class SubscriptionCreate(SubscriptionBase):
    """创建订阅请求"""
    payment_method: str  # stripe, paypal
    
class SubscriptionInDB(SubscriptionBase):
    """存储在数据库(JSON文件)中的订阅信息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True
    payment_id: Optional[str] = None
    payment_status: str = "pending"  # pending, completed, failed
    payment_details: Dict[str, Any] = Field(default_factory=dict)

class SubscriptionRead(SubscriptionBase):
    """API返回的订阅信息"""
    id: str
    user_id: str
    created_at: datetime
    expires_at: Optional[datetime]
    is_active: bool
    payment_status: str

class SubscriptionReadDetailed(SubscriptionRead):
    """详细的订阅信息，包括支付细节"""
    payment_id: Optional[str]
    payment_details: Dict[str, Any]

class SubscriptionUpdate(BaseModel):
    """更新订阅信息"""
    plan: Optional[str] = None
    is_active: Optional[bool] = None

class PaymentProcessing(BaseModel):
    """支付处理信息"""
    subscription_id: str
    success: bool
    payment_id: Optional[str] = None
    error_message: Optional[str] = None 