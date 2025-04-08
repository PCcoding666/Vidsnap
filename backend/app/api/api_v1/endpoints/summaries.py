from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Request, Response
from typing import Any, List, Dict
import logging
import traceback

from app.models.summary import SummaryCreate, SummaryRead, SummaryReadDetailed
from app.services.summary.video_service import create_summary, get_summary_by_id, get_summaries_by_user_id
from app.services.summary.summary_service import process_video_summary

# 配置日志
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("", response_model=SummaryRead)
async def create_video_summary(
    *,
    summary_in: SummaryCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
) -> Any:
    """
    创建新的视频摘要
    """
    try:
        # 记录请求信息
        logger.info(f"收到视频摘要请求: {summary_in.dict()}")
        
        # 创建摘要记录，使用默认用户ID
        summary = create_summary("default_user", summary_in)
        
        # 在后台任务中处理视频摘要
        background_tasks.add_task(process_video_summary, summary.id)
        
        logger.info(f"成功创建摘要记录，ID: {summary.id}")
        # 记录响应结构，用于调试前端问题
        response_data = summary.dict()
        logger.info(f"API返回结构: {response_data}")
        return summary
    except Exception as e:
        # 记录详细错误信息
        error_msg = f"创建视频摘要失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # 返回详细错误信息
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "创建视频摘要失败",
                "error": str(e),
                "error_type": e.__class__.__name__
            }
        )

@router.get("/{summary_id}", response_model=SummaryReadDetailed)
async def read_summary(
    *,
    summary_id: str,
) -> Any:
    """
    获取指定ID的摘要详情
    """
    try:
        logger.info(f"获取摘要详情请求，ID: {summary_id}")
        
        summary = get_summary_by_id(summary_id)
        if not summary:
            logger.warning(f"摘要不存在，ID: {summary_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "摘要不存在", "summary_id": summary_id}
            )
        
        # 记录响应结构，用于调试前端问题
        response_data = summary.dict()
        logger.info(f"API返回摘要详情结构: {response_data}")
        logger.info(f"成功获取摘要详情，ID: {summary_id}")
        return summary
    except HTTPException:
        raise
    except Exception as e:
        # 记录详细错误信息
        error_msg = f"获取摘要详情失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # 返回详细错误信息
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "获取摘要详情失败",
                "error": str(e),
                "error_type": e.__class__.__name__,
                "summary_id": summary_id
            }
        )

@router.get("/history/", response_model=List[SummaryReadDetailed])
async def read_summary_history(skip: int = 0, limit: int = 100) -> Any:
    """
    获取当前用户的摘要历史记录 (按创建时间降序排序)
    """
    # TODO: 实现用户认证后，从请求中获取 user_id
    user_id = "default_user" 
    logger.info(f"获取用户 {user_id} 的摘要历史记录请求, skip={skip}, limit={limit}")
    
    summaries = get_summaries_by_user_id(user_id)
    
    # 按创建时间降序排序
    sorted_summaries = sorted(summaries, key=lambda s: s.created_at, reverse=True)
    
    # 应用分页
    paginated_summaries = sorted_summaries[skip : skip + limit]
    
    logger.info(f"成功获取 {len(paginated_summaries)} 条历史记录")
    return paginated_summaries

# 可以添加删除历史记录的接口
# @router.delete("/{summary_id}", status_code=status.HTTP_204_NO_CONTENT)
# async def delete_summary_item(summary_id: str):
#     """
#     删除指定的摘要记录
#     """
#     # TODO: 实现用户认证，确保用户只能删除自己的记录
#     from app.services.summary.video_service import delete_summary
#     success = delete_summary(summary_id)
#     if not success:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")
#     logger.info(f"成功删除摘要记录，ID: {summary_id}")
#     return Response(status_code=status.HTTP_204_NO_CONTENT) 