"""
快速测试运行器
用于快速启动YouTube到OSS完整流程集成测试

使用方法：
    python run_test.py
"""
import sys
import subprocess
from pathlib import Path


def main():
    """运行集成测试"""
    # 获取测试文件路径
    test_file = Path(__file__).parent / "app" / "tests" / "test_video_to_oss_pipeline.py"
    
    if not test_file.exists():
        print(f"❌ 测试文件不存在: {test_file}")
        sys.exit(1)
    
    print("="*60)
    print("YouTube到OSS完整流程集成测试")
    print("="*60)
    print(f"测试文件: {test_file}")
    print("")
    
    # 构建pytest命令
    cmd = [
        sys.executable,  # 使用当前Python解释器
        "-m", "pytest",
        str(test_file),
        "-v",  # 详细输出
        "-s",  # 显示print输出
        "--tb=short",  # 简短的错误追踪
        "--asyncio-mode=auto",  # 自动asyncio模式
        "--color=yes"  # 彩色输出
    ]
    
    print(f"运行命令: {' '.join(cmd)}\n")
    
    # 运行测试
    try:
        result = subprocess.run(cmd, cwd=Path(__file__).parent)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 运行测试时发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
