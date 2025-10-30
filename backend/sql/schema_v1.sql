-- ============================================================================
-- Supabase Schema v1.0 - YouTube Video Analysis Platform
-- ============================================================================
-- 功能:
--   - 用户认证与资料管理
--   - 视频元数据存储
--   - 关键帧、转录、总结数据持久化
--   - 用户配额管理
--   - Row Level Security (RLS) 安全策略
-- ============================================================================

-- ============================================================================
-- 1. 用户资料表 (profiles)
-- ============================================================================
-- 扩展 Supabase 内置 auth.users 表,存储用户业务资料
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    username TEXT UNIQUE,
    full_name TEXT,
    avatar_url TEXT,
    subscription_tier TEXT NOT NULL DEFAULT 'free' CHECK (subscription_tier IN ('free', 'pro', 'enterprise')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_username ON public.profiles(username);

-- 启用 RLS
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- RLS 策略: 用户只能查看和更新自己的资料
CREATE POLICY users_can_view_own_profile ON public.profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY users_can_update_own_profile ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- 触发器: 自动更新 updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 2. 用户配额表 (user_quotas)
-- ============================================================================
-- 管理用户的月度视频处理配额和存储空间限制
CREATE TABLE IF NOT EXISTS public.user_quotas (
    user_id UUID PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
    monthly_video_limit INTEGER NOT NULL DEFAULT 10,
    monthly_videos_used INTEGER NOT NULL DEFAULT 0,
    total_storage_mb INTEGER NOT NULL DEFAULT 1000,
    used_storage_mb INTEGER NOT NULL DEFAULT 0,
    reset_date TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 约束: 使用量不能超过限额
    CHECK (monthly_videos_used >= 0),
    CHECK (used_storage_mb >= 0)
);

-- 启用 RLS
ALTER TABLE public.user_quotas ENABLE ROW LEVEL SECURITY;

-- RLS 策略: 用户只能查看自己的配额
CREATE POLICY users_can_view_own_quota ON public.user_quotas
    FOR SELECT USING (auth.uid() = user_id);

-- 触发器: 自动更新 updated_at
CREATE TRIGGER update_user_quotas_updated_at
    BEFORE UPDATE ON public.user_quotas
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 3. 视频信息主表 (videos)
-- ============================================================================
-- 存储视频的基本信息、处理状态和 OSS 资源链接
CREATE TABLE IF NOT EXISTS public.videos (
    video_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    duration REAL,
    source_type TEXT NOT NULL CHECK (source_type IN ('upload', 'youtube')),
    original_url TEXT,
    oss_video_url TEXT NOT NULL,
    oss_audio_url TEXT,
    video_format TEXT,
    video_size BIGINT,
    video_resolution TEXT,
    processing_status TEXT NOT NULL DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    processing_progress INTEGER NOT NULL DEFAULT 0 CHECK (processing_progress >= 0 AND processing_progress <= 100),
    error_message TEXT,
    upload_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_videos_user_id ON public.videos(user_id);
CREATE INDEX IF NOT EXISTS idx_videos_status ON public.videos(processing_status);
CREATE INDEX IF NOT EXISTS idx_videos_user_status ON public.videos(user_id, processing_status);
CREATE INDEX IF NOT EXISTS idx_videos_created_at ON public.videos(created_at DESC);

-- 启用 RLS
ALTER TABLE public.videos ENABLE ROW LEVEL SECURITY;

-- RLS 策略: 用户只能访问自己上传的视频
CREATE POLICY users_can_view_own_videos ON public.videos
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY users_can_insert_own_videos ON public.videos
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY users_can_update_own_videos ON public.videos
    FOR UPDATE USING (auth.uid() = user_id);

-- 触发器: 自动更新 updated_at
CREATE TRIGGER update_videos_updated_at
    BEFORE UPDATE ON public.videos
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 4. 关键帧表 (keyframes)
-- ============================================================================
-- 存储视频关键帧的时间戳和 OSS 图片 URL
CREATE TABLE IF NOT EXISTS public.keyframes (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES public.videos(video_id) ON DELETE CASCADE,
    frame_id INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    oss_image_url TEXT NOT NULL,
    scene_description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 唯一约束: 同一视频内帧 ID 唯一
    UNIQUE(video_id, frame_id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_keyframes_video_id ON public.keyframes(video_id);
CREATE INDEX IF NOT EXISTS idx_keyframes_timestamp ON public.keyframes(video_id, timestamp);

-- 启用 RLS
ALTER TABLE public.keyframes ENABLE ROW LEVEL SECURITY;

-- RLS 策略: 通过 videos 表的关联实现权限控制
CREATE POLICY users_can_view_own_keyframes ON public.keyframes
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.videos 
            WHERE videos.video_id = keyframes.video_id 
            AND videos.user_id = auth.uid()
        )
    );

-- ============================================================================
-- 5. 转录元数据表 (transcripts)
-- ============================================================================
-- 存储整体转录任务的元信息
CREATE TABLE IF NOT EXISTS public.transcripts (
    video_id TEXT PRIMARY KEY REFERENCES public.videos(video_id) ON DELETE CASCADE,
    language TEXT NOT NULL DEFAULT 'zh-CN',
    overall_confidence REAL,
    total_segments INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 启用 RLS
ALTER TABLE public.transcripts ENABLE ROW LEVEL SECURITY;

-- RLS 策略
CREATE POLICY users_can_view_own_transcripts ON public.transcripts
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.videos 
            WHERE videos.video_id = transcripts.video_id 
            AND videos.user_id = auth.uid()
        )
    );

-- ============================================================================
-- 6. 转录段落表 (transcript_segments)
-- ============================================================================
-- 存储视频音频转录的分段文本和时间信息
CREATE TABLE IF NOT EXISTS public.transcript_segments (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES public.videos(video_id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    confidence REAL,
    speaker_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 唯一约束: 同一视频内段落序号唯一
    UNIQUE(video_id, segment_index)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_transcript_segments_video_id ON public.transcript_segments(video_id);
CREATE INDEX IF NOT EXISTS idx_transcript_segments_time ON public.transcript_segments(video_id, start_time, end_time);
-- 全文搜索索引
CREATE INDEX IF NOT EXISTS idx_transcript_segments_text_search ON public.transcript_segments USING gin(to_tsvector('simple', text));

-- 启用 RLS
ALTER TABLE public.transcript_segments ENABLE ROW LEVEL SECURITY;

-- RLS 策略
CREATE POLICY users_can_view_own_transcript_segments ON public.transcript_segments
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.videos 
            WHERE videos.video_id = transcript_segments.video_id 
            AND videos.user_id = auth.uid()
        )
    );

-- ============================================================================
-- 7. 视频总结表 (video_summaries)
-- ============================================================================
-- 存储 AI 生成的多粒度视频总结
CREATE TABLE IF NOT EXISTS public.video_summaries (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES public.videos(video_id) ON DELETE CASCADE,
    summary_type TEXT NOT NULL CHECK (summary_type IN ('brief', 'standard', 'detailed')),
    content TEXT NOT NULL,
    model_used TEXT NOT NULL DEFAULT 'qwen3-vl-flash',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 唯一约束: 每种粒度只保留一份总结
    UNIQUE(video_id, summary_type)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_video_summaries_video_id ON public.video_summaries(video_id);

-- 启用 RLS
ALTER TABLE public.video_summaries ENABLE ROW LEVEL SECURITY;

-- RLS 策略
CREATE POLICY users_can_view_own_summaries ON public.video_summaries
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.videos 
            WHERE videos.video_id = video_summaries.video_id 
            AND videos.user_id = auth.uid()
        )
    );

-- ============================================================================
-- 8. 数据库函数
-- ============================================================================

-- 递增月度视频使用次数
CREATE OR REPLACE FUNCTION increment_monthly_videos(p_user_id UUID)
RETURNS void AS $$
BEGIN
    UPDATE public.user_quotas 
    SET monthly_videos_used = monthly_videos_used + 1,
        updated_at = NOW()
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 更新存储使用量
CREATE OR REPLACE FUNCTION update_storage_usage(p_user_id UUID, p_size_mb INTEGER)
RETURNS void AS $$
BEGIN
    UPDATE public.user_quotas 
    SET used_storage_mb = used_storage_mb + p_size_mb,
        updated_at = NOW()
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- 9. 触发器: 自动创建用户资料和配额
-- ============================================================================
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
    default_username TEXT;
BEGIN
    -- 生成默认用户名
    default_username := 'user_' || substring(NEW.id::text, 1, 8);
    
    -- 创建 profiles 记录
    INSERT INTO public.profiles (id, email, username, subscription_tier)
    VALUES (
        NEW.id, 
        NEW.email, 
        default_username,
        'free'
    )
    ON CONFLICT (id) DO NOTHING;
    
    -- 创建 user_quotas 记录
    INSERT INTO public.user_quotas (
        user_id, 
        monthly_video_limit, 
        total_storage_mb, 
        reset_date
    )
    VALUES (
        NEW.id,
        10,  -- 免费用户默认 10 个视频/月
        1000,  -- 免费用户默认 1GB 存储空间
        date_trunc('month', CURRENT_DATE) + interval '1 month'
    )
    ON CONFLICT (user_id) DO NOTHING;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 创建触发器(仅当不存在时)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger 
        WHERE tgname = 'on_auth_user_created'
    ) THEN
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW
            EXECUTE FUNCTION handle_new_user();
    END IF;
END;
$$;

-- ============================================================================
-- 10. Schema 版本管理
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.schema_versions (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description TEXT
);

-- 记录当前版本
INSERT INTO public.schema_versions (version, description)
VALUES ('1.0', 'Initial schema: 用户管理、视频元数据、关键帧、转录、总结')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- 初始化完成
-- ============================================================================
