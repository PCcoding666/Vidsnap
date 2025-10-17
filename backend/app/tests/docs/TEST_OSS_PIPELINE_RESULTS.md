# YouTube视频到OSS存储 - 端到端集成测试报告
**测试时间**: 2025-10-17 11:13:05
**测试视频URL**: https://www.youtube.com/watch?v=1PaoWKvcJP0

---

## 📊 测试概览
- **总体状态**: ✅ 成功
- **总耗时**: 26.47 秒
- **视频ID**: 585306ed-c205-4a18-b58b-c1d67872fc59

## 🔄 执行阶段
### ✅ OSS服务检查
- **状态**: 成功
- **耗时**: 0.00 秒
- **详情**: OSS Bucket: yt-summerizer-aliyun

### ✅ YouTube视频下载
- **状态**: 成功
- **耗时**: 26.47 秒
- **详情**: 视频ID: 585306ed-c205-4a18-b58b-c1d67872fc59

### ✅ 关键帧提取
- **状态**: 成功
- **耗时**: 0.00 秒
- **详情**: 提取了10个关键帧

### ✅ OSS上传验证
- **状态**: 成功
- **耗时**: 0.00 秒
- **详情**: 视频和10个关键帧均已上传OSS

### ✅ URL可访问性
- **状态**: 成功
- **耗时**: 1.84 秒
- **详情**: 10/10 可访问 (100.0%)

### ✅ 临时文件清理
- **状态**: 成功
- **耗时**: 0.00 秒
- **详情**: 清理了12个文件

## 🖼️ 关键帧信息
**提取数量**: 10 帧

| 序号 | 时间戳 | OSS URL | 可访问性 |
|------|--------|---------|----------|
| 1 | 6.69s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 2 | 20.06s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 3 | 33.43s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 4 | 46.80s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 5 | 60.17s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 6 | 73.54s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 7 | 86.91s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 8 | 100.28s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 9 | 113.65s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |
| 10 | 127.02s | https://yt-summerizer-aliyun.oss-cn-hangzhou.al... | ✅ |

## 🌐 URL可访问性测试
- **总URL数量**: 10
- **可访问数量**: 10
- **不可访问数量**: 0
- **可访问率**: 100.0%

## 🧹 清理操作
- **状态**: 成功
- **清理文件数**: 12

## 📝 测试结论
✅ **所有测试通过！** 完整的YouTube到OSS流程验证成功。

---
*报告生成时间: 2025-10-17 11:13:05*
