# 并发执行关键帧提取与音频转录设计

## 1. 设计目标

在 VideoProcessingPipeline 内部实现下载后的两个独立阶段（关键帧提取和音频转录）的并发执行，以缩短单个任务的总处理时间 (Latency)。

### 1.1 优化目标

- **降低处理延迟**：通过并发执行减少任务的总等待时间
- **提高资源利用率**：充分利用 I/O 等待时间执行其他任务
- **保持错误处理健壮性**：确保任何并发任务失败都能被正确捕获和处理
- **维护数据完整性**：确保并发结果正确合并后传递给后续流程

## 2. 现状分析

### 2.1 当前处理流程

当前 `AliyunVideoProcessingPipeline.process_video_with_summary()` 采用**串行处理**模式：

```
步骤 1: 视频下载与上传
  ├─ YouTube 下载 或 用户上传文件处理
  ├─ 上传视频到 OSS
  └─ 提取关键帧（使用场景检测）
      ↓
步骤 2: 音频转录（等待步骤 1 完全完成）
  ├─ 提取音频（ffmpeg）
  ├─ 上传音频到 OSS
  └─ Paraformer 语音识别
      ↓
步骤 3: 生成 Metadata
      ↓
步骤 4: LLM 视频总结
      ↓
步骤 5: 上传 Metadata 到 OSS
      ↓
步骤 6: 清理临时文件
```

### 2.2 瓶颈分析

| 阶段 | 当前耗时特征 | I/O 特性 |
|------|-------------|----------|
| 关键帧提取 | 场景检测 + 帧提取 + OSS 上传，约 20-60 秒 | I/O 密集（磁盘读取 + 网络上传） |
| 音频转录 | 音频提取 + OSS 上传 + Paraformer API 调用，约 30-120 秒 | I/O 密集（磁盘读写 + 网络 I/O + 远程 API 等待） |

**关键发现**：
- 关键帧提取和音频转录两个阶段都属于 **I/O 密集型** 操作
- 两者之间 **没有数据依赖关系**，可以并发执行
- 当前串行执行导致总等待时间 = 关键帧耗时 + 音频转录耗时
- 并发执行后理论总等待时间 = max(关键帧耗时, 音频转录耗时)

### 2.3 涉及的核心服务方法

| 服务类 | 方法 | 功能 | 调用位置 |
|--------|------|------|----------|
| `AliyunVideoService` | `extract_keyframes_scene_detection()` | 场景检测并提取关键帧 | `process_video_dual_source()` 内部 |
| `ParaformerSpeechService` | `extract_and_transcribe_audio()` | 提取音频并转录 | `process_video_with_summary()` 步骤 2 |

## 3. 并发执行设计

### 3.1 并发技术选型

#### 方案对比

| 方案 | 优势 | 劣势 | 是否采用 |
|------|------|------|----------|
| `concurrent.futures.ThreadPoolExecutor` | 简单易用，适合 I/O 密集型任务，已有异步代码可用 `run_in_executor` 包装 | Python GIL 限制（但 I/O 操作会释放 GIL） | ✅ **推荐** |
| `asyncio.gather()` | 原生异步，代码一致性好，已有 async 方法可直接使用 | 需要所有方法都是 async | ✅ **推荐** |
| `concurrent.futures.ProcessPoolExecutor` | 绕过 GIL，适合 CPU 密集型 | 进程间通信开销大，序列化复杂对象困难 | ❌ 不适用 |

#### 最终方案

**采用 `asyncio.gather()` 方案**，理由如下：
- 当前代码已全部使用 `async/await` 模式
- `AliyunVideoService.extract_keyframes_scene_detection()` 和 `ParaformerSpeechService.extract_and_transcribe_audio()` 都已是异步方法
- 代码风格统一，无需混合多种并发模型
- `asyncio.gather()` 提供简洁的异常处理和结果收集机制

### 3.2 并发执行时机调整

#### 当前流程改造

**改造前**（步骤 1 内部已包含关键帧提取）：
```
步骤 1: process_video_dual_source()
  ├─ 下载/上传视频
  ├─ 上传视频到 OSS
  └─ 提取关键帧 ← 在这里完成
      ↓
步骤 2: extract_and_transcribe_audio() ← 等待步骤 1 完成
```

**改造后**：
```
步骤 1a: process_video_dual_source()（修改）
  ├─ 下载/上传视频
  └─ 上传视频到 OSS
      ↓
步骤 1b: 并发执行区
  ├─ 任务 A: extract_keyframes_scene_detection() ─┐
  └─ 任务 B: extract_and_transcribe_audio()       ├─ asyncio.gather()
                                                    ↓
                                      等待两个任务都完成
                                                    ↓
步骤 2: 合并结果并继续后续流程
```

### 3.3 代码结构设计

#### 3.3.1 `AliyunVideoService.process_video_dual_source()` 修改

**修改内容**：
- 移除步骤 3 中的关键帧提取逻辑
- 仅返回视频路径和基础信息，将关键帧提取延迟到 Pipeline 层

**修改后返回数据结构**：
```
{
    "status": "success",
    "video_id": "xxx",
    "video_info": VideoInfo 对象,
    "video_path": "/path/to/video.mp4",  ← 新增，用于后续并发任务
    "video_metadata": {...},
    "session_temp_dir": "/tmp/session_xxx"
}
```

#### 3.3.2 `AliyunVideoProcessingPipeline.process_video_with_summary()` 并发逻辑

**并发执行代码结构**：

```
伪代码展示：

# 步骤 1: 下载/上传视频（已完成）
video_result = await video_service.process_video_dual_source(...)
video_path = video_result["video_path"]
video_id = video_result["video_id"]

# 步骤 2: 并发执行关键帧提取和音频转录
try:
    keyframes, transcript_result = await asyncio.gather(
        video_service.extract_keyframes_scene_detection(
            video_path, video_id, session_temp_dir
        ),
        speech_service.extract_and_transcribe_audio(
            video_path, video_id
        ),
        return_exceptions=False  # 任何异常会立即抛出
    )
except Exception as e:
    # 捕获并发任务中的异常
    处理错误并更新 Supabase 状态为 FAILED
    返回错误信息
    
# 步骤 3: 验证并发结果
if not keyframes:
    记录警告："关键帧提取失败"
    keyframes = []  # 使用空列表继续

if not transcript_result:
    记录警告："音频转录失败"
    transcript_result = _create_empty_transcript()

# 步骤 4: 继续后续流程（生成 Metadata、LLM 总结等）
```

### 3.4 错误处理策略

#### 3.4.1 并发任务异常处理机制

| 错误场景 | 处理策略 | Supabase 状态更新 |
|---------|---------|-------------------|
| 关键帧提取失败 | 使用空列表继续，记录警告日志 | 不中断流程，标记 `keyframes_count=0` |
| 音频转录失败 | 使用空转录对象继续，记录警告日志 | 不中断流程，标记 `transcript_segments_count=0` |
| 两个任务都失败 | 视为严重错误，终止流程 | 更新状态为 `failed`，记录详细错误信息 |
| 任务异常崩溃（未捕获） | `asyncio.gather()` 立即抛出异常 | 更新状态为 `failed`，记录堆栈信息 |

#### 3.4.2 异常传播路径

```
并发任务异常
    ↓
asyncio.gather() 捕获
    ↓
外层 try-except 块
    ↓
日志记录 + Supabase 状态更新
    ↓
返回 {"status": "error", "error": "详细错误信息"}
```

#### 3.4.3 错误日志记录规范

**日志级别定义**：
- `ERROR`：并发任务完全失败，影响后续流程
- `WARNING`：单个任务失败但可降级处理
- `INFO`：并发执行的关键进度节点

**关键日志点**：
1. 并发任务启动前：记录 `INFO` 级别日志，包含任务名称
2. 单个任务失败：记录 `WARNING` 级别日志，包含任务名称和错误概要
3. 并发区异常退出：记录 `ERROR` 级别日志，包含完整堆栈
4. 并发任务全部成功：记录 `INFO` 级别日志，包含耗时统计

### 3.5 性能监控设计

#### 时间统计指标

| 指标名称 | 计算方式 | 用途 |
|---------|---------|------|
| `keyframes_duration` | 关键帧提取任务结束时间 - 开始时间 | 评估关键帧提取性能 |
| `transcription_duration` | 音频转录任务结束时间 - 开始时间 | 评估音频转录性能 |
| `concurrent_total_duration` | 并发区结束时间 - 并发区开始时间 | 评估并发执行效果 |
| `latency_improvement` | (串行耗时 - 并发耗时) / 串行耗时 × 100% | 量化优化效果 |

**日志输出示例**：
```
[INFO] 并发执行完成 - 关键帧: 45.2s, 音频转录: 78.3s, 总耗时: 78.5s (节省 44.8s)
```

## 4. 数据流与状态管理

### 4.1 并发结果合并

#### 合并逻辑

```
并发执行结果 (keyframes, transcript_result)
    ↓
结果验证与降级处理
    ├─ keyframes 为空 → 使用 []
    └─ transcript_result 为空 → 使用 _create_empty_transcript()
    ↓
传递给 _generate_unified_metadata()
    ↓
生成统一 Metadata 对象
```

### 4.2 Supabase 进度更新时机

| 时间点 | 进度值 | 状态 | 说明 |
|--------|--------|------|------|
| 视频下载完成 | 15% | processing | 视频已上传到 OSS |
| 并发区开始前 | 20% | processing | 准备并发执行 |
| 并发区完成后 | 60% | processing | 关键帧和转录都已完成 |
| LLM 总结完成 | 80% | processing | AI 总结生成完成 |
| 全部流程完成 | 100% | completed | 处理成功 |

**注意**：并发区内部不应更新 Supabase 状态，避免竞态条件。

### 4.3 数据完整性保证

#### 完整性检查清单

- [ ] 关键帧列表不为 None（可以为空列表）
- [ ] 转录对象不为 None（可以是空转录对象）
- [ ] 所有必填字段都已填充
- [ ] OSS URL 格式有效（非空且符合 URL 格式）
- [ ] 时间戳数据类型正确（float 类型）

## 5. 实现约束

### 5.1 不可修改的部分

- `SimpleLLMService` 接口和调用方式
- Supabase 数据模型结构
- OSS 上传服务接口
- 已有的错误处理基础设施

### 5.2 必须保留的功能

- 完整的错误日志记录
- 进度回调机制（`progress_callback`）
- 临时文件清理逻辑
- Supabase 集成点的状态更新

### 5.3 性能约束

- 并发任务数量固定为 2（关键帧 + 音频转录）
- 不增加额外的 API 调用次数
- 不改变 OSS 上传的并发策略（已在各服务内部实现）

## 6. 验证标准

### 6.1 功能验证

#### 验证场景

| 验证场景 | 预期行为 | 验证方法 |
|---------|---------|---------|
| 正常并发执行 | 两个任务并发完成，结果正确合并 | 检查日志时间戳，确认并发执行 |
| 关键帧提取失败 | 使用空列表继续，生成包含转录的 Metadata | 模拟关键帧提取异常，检查返回结果 |
| 音频转录失败 | 使用空转录对象继续，生成包含关键帧的 Metadata | 模拟转录服务不可用，检查返回结果 |
| 并发区完全失败 | 整个流程中止，Supabase 状态更新为 `failed` | 模拟两个任务都抛出异常 |

### 6.2 性能验证

#### 性能基准

**测试视频规格**：
- 时长：5 分钟
- 分辨率：1080p
- 来源：YouTube

**性能目标**：
- 并发执行总耗时 < max(关键帧耗时, 音频转录耗时) + 5 秒（考虑任务调度开销）
- 延迟改善率 > 30%（相比串行执行）

### 6.3 数据验证

#### 验证清单

- [ ] 关键帧数量与预期一致（场景检测结果）
- [ ] 转录段落数量 > 0（非空音频情况下）
- [ ] Metadata 中 `keyframes` 和 `transcript` 字段完整
- [ ] 所有 OSS URL 可访问
- [ ] 时间戳数据类型正确且范围合理

## 7. 风险与缓解

### 7.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 并发任务资源竞争 | 性能下降或超时 | 限制并发数为 2，避免过度并发 |
| 异常未被正确捕获 | 流程中断，数据丢失 | 使用 `asyncio.gather()` 统一异常处理，外层 try-except 兜底 |
| 临时文件清理时机不当 | 磁盘空间浪费 | 确保并发区完成后才清理，使用 try-finally 保证执行 |
| Supabase 状态更新竞态 | 进度显示不准确 | 并发区内部不更新状态，仅在明确的同步点更新 |

### 7.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 关键帧和转录都失败 | 无法生成有效 Metadata | 视为严重错误终止流程，明确告知用户 |
| 部分任务成功但结果质量差 | 后续 LLM 总结质量下降 | 记录置信度等质量指标，供 LLM 服务参考 |

## 8. 后续优化方向

### 8.1 短期优化（当前范围外）

- 在 OSS 上传阶段也引入并发（分片并发上传）
- 对 LLM 关键帧分析引入批量并发处理

### 8.2 长期优化

- 引入任务队列系统（Celery），支持分布式并发
- 实现自适应并发度调整（根据系统负载动态调整）
- 增加缓存机制，避免重复处理相同视频

## 9. 总结

本设计通过在 `AliyunVideoProcessingPipeline` 中引入 `asyncio.gather()` 并发执行关键帧提取和音频转录两个独立阶段，预期可将单任务处理延迟降低 30% 以上。设计充分考虑了错误处理、数据完整性和状态管理的复杂性，确保在提升性能的同时保持系统稳定性。
