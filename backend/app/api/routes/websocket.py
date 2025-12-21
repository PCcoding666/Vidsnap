"""
WebSocket 实时推送端点
替代 Supabase Realtime，实现本地实时消息推送
"""
import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from starlette.websockets import WebSocketState

from app.core.logging import logger
from app.core.auth import verify_jwt_token

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """
    WebSocket 连接管理器
    管理所有活跃的 WebSocket 连接
    """
    
    def __init__(self):
        # 视频进度连接: {video_id: {user_id: websocket}}
        self.video_connections: Dict[str, Dict[str, WebSocket]] = {}
        # 用户通知连接: {user_id: set(websocket)}
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        # 心跳间隔（秒）
        self.heartbeat_interval = 30
    
    async def connect_video(self, websocket: WebSocket, video_id: str, user_id: str):
        """连接到视频进度更新"""
        await websocket.accept()
        
        if video_id not in self.video_connections:
            self.video_connections[video_id] = {}
        
        self.video_connections[video_id][user_id] = websocket
        logger.info(f"🔌 WebSocket 连接 (视频): {video_id} - 用户 {user_id}")
    
    async def connect_user(self, websocket: WebSocket, user_id: str):
        """连接到用户通知"""
        await websocket.accept()
        
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        
        self.user_connections[user_id].add(websocket)
        logger.info(f"🔌 WebSocket 连接 (通知): 用户 {user_id}")
    
    def disconnect_video(self, video_id: str, user_id: str):
        """断开视频进度连接"""
        if video_id in self.video_connections:
            self.video_connections[video_id].pop(user_id, None)
            if not self.video_connections[video_id]:
                del self.video_connections[video_id]
        logger.info(f"🔌 WebSocket 断开 (视频): {video_id} - 用户 {user_id}")
    
    def disconnect_user(self, websocket: WebSocket, user_id: str):
        """断开用户通知连接"""
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        logger.info(f"🔌 WebSocket 断开 (通知): 用户 {user_id}")
    
    async def send_video_progress(
        self, 
        video_id: str, 
        status: str, 
        progress: int,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        发送视频处理进度更新
        
        Args:
            video_id: 视频 ID
            status: 处理状态 (pending/processing/completed/failed)
            progress: 处理进度 (0-100)
            message: 可选消息
            data: 可选附加数据
        """
        if video_id not in self.video_connections:
            return
        
        payload = {
            "type": "video_progress",
            "video_id": video_id,
            "status": status,
            "progress": progress,
            "message": message,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        disconnected = []
        for user_id, websocket in self.video_connections[video_id].items():
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(payload)
                else:
                    disconnected.append(user_id)
            except Exception as e:
                logger.error(f"❌ 发送视频进度失败: {e}")
                disconnected.append(user_id)
        
        # 清理断开的连接
        for user_id in disconnected:
            self.disconnect_video(video_id, user_id)
    
    async def send_user_notification(
        self, 
        user_id: str, 
        notification_type: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        发送用户通知
        
        Args:
            user_id: 用户 ID
            notification_type: 通知类型 (video_completed/subscription_update/system)
            title: 通知标题
            message: 通知内容
            data: 可选附加数据
        """
        if user_id not in self.user_connections:
            return
        
        payload = {
            "type": "notification",
            "notification_type": notification_type,
            "title": title,
            "message": message,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        disconnected = []
        for websocket in self.user_connections[user_id]:
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(payload)
                else:
                    disconnected.append(websocket)
            except Exception as e:
                logger.error(f"❌ 发送用户通知失败: {e}")
                disconnected.append(websocket)
        
        # 清理断开的连接
        for ws in disconnected:
            self.disconnect_user(ws, user_id)
    
    async def broadcast_to_video(self, video_id: str, message: Dict[str, Any]):
        """广播消息给所有观看该视频的用户"""
        if video_id not in self.video_connections:
            return
        
        disconnected = []
        for user_id, websocket in self.video_connections[video_id].items():
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
                else:
                    disconnected.append(user_id)
            except Exception:
                disconnected.append(user_id)
        
        for user_id in disconnected:
            self.disconnect_video(video_id, user_id)


# 全局连接管理器
manager = ConnectionManager()


async def authenticate_websocket(token: str) -> Optional[Dict[str, Any]]:
    """验证 WebSocket 连接的 Token"""
    if not token:
        return None
    return verify_jwt_token(token)


@router.websocket("/video/{video_id}/progress")
async def video_progress_websocket(
    websocket: WebSocket,
    video_id: str,
    token: str = Query(..., description="JWT Token")
):
    """
    视频处理进度 WebSocket 端点
    
    连接后会收到视频处理进度更新：
    {
        "type": "video_progress",
        "video_id": "xxx",
        "status": "processing",
        "progress": 50,
        "message": "正在转录...",
        "timestamp": "2024-01-01T00:00:00"
    }
    
    客户端可以发送心跳消息保持连接：
    {"type": "ping"}
    
    服务器会响应：
    {"type": "pong"}
    """
    # 验证 Token
    user = await authenticate_websocket(token)
    if not user:
        await websocket.close(code=4001, reason="认证失败")
        return
    
    user_id = user.get("id")
    
    # 连接
    await manager.connect_video(websocket, video_id, user_id)
    
    try:
        # 发送连接成功消息
        await websocket.send_json({
            "type": "connected",
            "video_id": video_id,
            "message": "已连接到视频进度更新",
        })
        
        # 持续监听客户端消息
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=manager.heartbeat_interval * 2
                )
                
                # 处理心跳
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
            except asyncio.TimeoutError:
                # 发送心跳检测
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"❌ WebSocket 错误: {e}")
    finally:
        manager.disconnect_video(video_id, user_id)


@router.websocket("/notifications")
async def notifications_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT Token")
):
    """
    用户通知 WebSocket 端点
    
    连接后会收到各种通知：
    {
        "type": "notification",
        "notification_type": "video_completed",
        "title": "视频处理完成",
        "message": "您的视频已处理完成",
        "data": {"video_id": "xxx"},
        "timestamp": "2024-01-01T00:00:00"
    }
    
    支持的通知类型:
    - video_completed: 视频处理完成
    - subscription_update: 订阅频道有新视频
    - system: 系统通知
    """
    # 验证 Token
    user = await authenticate_websocket(token)
    if not user:
        await websocket.close(code=4001, reason="认证失败")
        return
    
    user_id = user.get("id")
    
    # 连接
    await manager.connect_user(websocket, user_id)
    
    try:
        # 发送连接成功消息
        await websocket.send_json({
            "type": "connected",
            "message": "已连接到通知服务",
        })
        
        # 持续监听客户端消息
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=manager.heartbeat_interval * 2
                )
                
                # 处理心跳
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
            except asyncio.TimeoutError:
                # 发送心跳检测
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"❌ WebSocket 错误: {e}")
    finally:
        manager.disconnect_user(websocket, user_id)


# ============================================
# 便捷方法供其他模块调用
# ============================================

async def notify_video_progress(
    video_id: str, 
    status: str, 
    progress: int,
    message: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
):
    """
    发送视频进度通知（供其他模块调用）
    
    示例：
        from app.api.routes.websocket import notify_video_progress
        await notify_video_progress("video123", "processing", 50, "正在转录...")
    """
    await manager.send_video_progress(video_id, status, progress, message, data)


async def notify_user(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None
):
    """
    发送用户通知（供其他模块调用）
    
    示例：
        from app.api.routes.websocket import notify_user
        await notify_user(
            user_id="xxx",
            notification_type="video_completed",
            title="视频处理完成",
            message="您的视频已处理完成",
            data={"video_id": "xxx"}
        )
    """
    await manager.send_user_notification(user_id, notification_type, title, message, data)

