#!/usr/bin/env python3
"""
OSS URL 诊断脚本
用于检查 OSS URL 的可访问性和配置
"""
import os
import sys
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def check_oss_config():
    """检查 OSS 配置"""
    print("="*60)
    print("阿里云 OSS 配置检查")
    print("="*60)
    
    config = {
        'ALIYUN_ACCESS_KEY_ID': os.getenv('ALIYUN_ACCESS_KEY_ID'),
        'ALIYUN_ACCESS_KEY_SECRET': os.getenv('ALIYUN_ACCESS_KEY_SECRET'),
        'ALIYUN_OSS_ENDPOINT': os.getenv('ALIYUN_OSS_ENDPOINT'),
        'ALIYUN_OSS_BUCKET': os.getenv('ALIYUN_OSS_BUCKET'),
    }
    
    print("\n📋 当前配置:")
    for key, value in config.items():
        if value:
            if 'SECRET' in key or 'KEY' in key:
                display_value = value[:4] + '...' + value[-4:] if len(value) > 8 else '***'
            else:
                display_value = value
            print(f"  ✅ {key}: {display_value}")
        else:
            print(f"  ❌ {key}: 未设置")
    
    # 检查endpoint格式
    endpoint = config['ALIYUN_OSS_ENDPOINT']
    bucket_name = config['ALIYUN_OSS_BUCKET']
    
    if endpoint and bucket_name:
        print("\n🔗 URL 构造分析:")
        
        # 清理endpoint
        clean_endpoint = endpoint.replace('https://', '').replace('http://', '')
        print(f"  原始 Endpoint: {endpoint}")
        print(f"  清理后 Endpoint: {clean_endpoint}")
        
        # 构造示例URL
        sample_object_key = "videos/20251017/test-video-id/keyframes/frame_000.jpg"
        sample_url = f"https://{bucket_name}.{clean_endpoint}/{sample_object_key}"
        
        print(f"  Bucket名称: {bucket_name}")
        print(f"  示例对象键: {sample_object_key}")
        print(f"  构造的URL: {sample_url}")
        
        return sample_url
    
    return None


def test_url_accessibility(url: str):
    """测试URL可访问性"""
    print("\n" + "="*60)
    print("URL 可访问性测试")
    print("="*60)
    
    print(f"\n🔍 测试URL: {url}")
    
    # 测试1: HEAD请求
    print("\n[测试1] HEAD 请求...")
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        print(f"  状态码: {response.status_code}")
        print(f"  响应头: {dict(list(response.headers.items())[:5])}")
        
        if response.status_code == 200:
            print("  ✅ HEAD 请求成功")
        elif response.status_code == 403:
            print("  ❌ 403 Forbidden - Bucket 可能未设置为公共读")
        elif response.status_code == 404:
            print("  ❌ 404 Not Found - 文件不存在（正常，这只是示例URL）")
        else:
            print(f"  ⚠️ 状态码 {response.status_code}")
            
    except requests.RequestException as e:
        print(f"  ❌ 请求失败: {e}")
    
    # 测试2: GET请求
    print("\n[测试2] GET 请求...")
    try:
        response = requests.get(url, timeout=10, stream=True)
        print(f"  状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("  ✅ GET 请求成功")
            # 尝试读取少量数据
            chunk = next(response.iter_content(chunk_size=100), None)
            if chunk:
                print(f"  数据大小: {len(chunk)} bytes")
        elif response.status_code == 403:
            print("  ❌ 403 Forbidden - Bucket 访问权限问题")
            print("\n  💡 解决方案:")
            print("     1. 登录阿里云OSS控制台")
            print("     2. 找到您的 Bucket")
            print("     3. 进入【权限管理】→【读写权限】")
            print("     4. 设置为【公共读】")
        elif response.status_code == 404:
            print("  ℹ️ 404 Not Found - 这是示例URL，文件不存在是正常的")
            print("  ✅ 但这说明 Bucket 本身是可访问的！")
        else:
            print(f"  ⚠️ 状态码 {response.status_code}")
            
        response.close()
        
    except requests.RequestException as e:
        print(f"  ❌ 请求失败: {e}")


def test_actual_keyframe_url():
    """测试实际的关键帧URL（如果存在）"""
    print("\n" + "="*60)
    print("实际关键帧URL测试")
    print("="*60)
    
    # 从测试报告中获取实际URL
    test_url = input("\n请输入一个实际的关键帧URL（或按回车跳过）: ").strip()
    
    if test_url:
        print(f"\n🔍 测试实际URL: {test_url}")
        
        try:
            response = requests.get(test_url, timeout=10)
            print(f"  状态码: {response.status_code}")
            
            if response.status_code == 200:
                print("  ✅ URL 可访问！")
                print(f"  Content-Type: {response.headers.get('Content-Type', 'N/A')}")
                print(f"  Content-Length: {response.headers.get('Content-Length', 'N/A')} bytes")
            elif response.status_code == 403:
                print("  ❌ 403 Forbidden - 请检查 Bucket 权限设置")
            elif response.status_code == 404:
                print("  ❌ 404 Not Found - 文件不存在或路径错误")
            else:
                print(f"  ⚠️ 状态码 {response.status_code}")
                
        except requests.RequestException as e:
            print(f"  ❌ 请求失败: {e}")


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🔧 阿里云 OSS URL 诊断工具")
    print("="*60)
    
    # 1. 检查配置
    sample_url = check_oss_config()
    
    if not sample_url:
        print("\n❌ OSS 配置不完整，无法继续测试")
        sys.exit(1)
    
    # 2. 测试URL可访问性
    test_url_accessibility(sample_url)
    
    # 3. 测试实际URL（可选）
    test_actual_keyframe_url()
    
    # 4. 总结
    print("\n" + "="*60)
    print("📝 诊断总结")
    print("="*60)
    print("\n如果看到 403 错误，请执行以下步骤：")
    print("1. 登录阿里云控制台: https://oss.console.aliyun.com/")
    print("2. 选择您的 Bucket")
    print("3. 点击【权限管理】→【读写权限】")
    print("4. 设置为【公共读】")
    print("5. 保存后等待1-2分钟生效")
    print("\n如果看到 404 错误但没有 403，说明 Bucket 配置正确！")
    print("测试失败可能是因为测试时文件还未上传。")
    print("="*60)


if __name__ == "__main__":
    main()
