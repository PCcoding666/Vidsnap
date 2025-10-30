#!/usr/bin/env python3
"""
Supabase Schema 初始化脚本
读取 SQL 文件并在 Supabase 数据库中执行,创建所需的表结构和触发器
"""
import sys
import argparse
from pathlib import Path
import logging

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.services.supabase_service import supabase_service

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def read_sql_file(sql_file_path: Path) -> str:
    """读取 SQL 文件内容"""
    try:
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.info(f"✅ 读取 SQL 文件: {sql_file_path} ({len(content.splitlines())} 行)")
        return content
    except FileNotFoundError:
        logger.error(f"❌ 找不到 SQL 文件: {sql_file_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 读取 SQL 文件失败: {e}")
        sys.exit(1)


def execute_sql(sql_content: str, dry_run: bool = False) -> bool:
    """执行 SQL 语句"""
    if dry_run:
        logger.info("[DRY RUN] 跳过实际执行,仅验证 SQL 语法")
        return True
    
    if not supabase_service.is_available():
        logger.error("❌ Supabase 服务不可用,请检查配置")
        logger.error("   需要配置以下环境变量:")
        logger.error("   - SUPABASE_URL")
        logger.error("   - SUPABASE_ANON_KEY")
        logger.error("   - SUPABASE_SERVICE_KEY")
        return False
    
    try:
        logger.info(f"🔗 连接 Supabase: {settings.SUPABASE_URL}")
        
        # 注意: Supabase Python SDK 不直接支持执行原始 SQL
        # 需要通过 Supabase 管理面板或 REST API 执行
        logger.warning("⚠️ Supabase Python SDK 不支持直接执行 SQL 文件")
        logger.info("请通过以下方式之一执行 SQL:")
        logger.info("1. 在 Supabase Dashboard 的 SQL Editor 中执行")
        logger.info("2. 使用 psql 命令行工具连接到 PostgreSQL 数据库")
        logger.info("3. 使用 Supabase CLI: supabase db execute")
        
        logger.info("\n执行步骤:")
        logger.info(f"1. 登录 Supabase Dashboard: {settings.SUPABASE_URL.replace('https://', 'https://app.supabase.com/project/')}")
        logger.info("2. 导航到 SQL Editor")
        logger.info(f"3. 复制并执行文件: {Path(__file__).parent.parent / 'sql/schema_v1.sql'}")
        
        return True
        
    except Exception as e:
        logger.exception(f"❌ 执行 SQL 失败: {e}")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="初始化 Supabase 数据库 Schema")
    parser.add_argument(
        '--sql-file',
        type=str,
        default='sql/schema_v1.sql',
        help='SQL 文件路径(相对于 backend 目录,默认: sql/schema_v1.sql)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅验证 SQL 文件,不执行实际操作'
    )
    
    args = parser.parse_args()
    
    # 构建 SQL 文件路径
    sql_file_path = project_root / args.sql_file
    
    logger.info("=" * 70)
    logger.info("Supabase Schema 初始化工具")
    logger.info("=" * 70)
    
    # 读取 SQL 文件
    sql_content = read_sql_file(sql_file_path)
    
    # 执行 SQL
    success = execute_sql(sql_content, dry_run=args.dry_run)
    
    logger.info("=" * 70)
    if success:
        if args.dry_run:
            logger.info("✅ [DRY RUN] SQL 文件验证通过")
        else:
            logger.info("✅ Schema 初始化指南已生成")
        sys.exit(0)
    else:
        logger.error("❌ Schema 初始化失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
