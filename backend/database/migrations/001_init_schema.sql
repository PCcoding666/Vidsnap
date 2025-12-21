-- VidSnap Database Schema v1.0
-- 本地 PostgreSQL 初始化脚本
-- 替代 Supabase，自主管理用户和业务数据

-- 启用必要的扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- 用户认证表 (替代 Supabase auth.users)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_superuser BOOLEAN NOT NULL DEFAULT false,
    is_verified BOOLEAN NOT NULL DEFAULT false,
    
    -- OAuth 相关
    oauth_provider VARCHAR(50),
    oauth_account_id VARCHAR(255),
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 用户 OAuth 账号关联表
CREATE TABLE IF NOT EXISTS oauth_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    oauth_name VARCHAR(100) NOT NULL,
    access_token VARCHAR(1024) NOT NULL,
    expires_at INTEGER,
    refresh_token VARCHAR(1024),
    account_id VARCHAR(320) NOT NULL,
    account_email VARCHAR(320),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    UNIQUE(oauth_name, account_id)
);

-- ============================================
-- 用户资料表
-- ============================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    username TEXT UNIQUE,
    full_name TEXT,
    avatar_url TEXT,
    subscription_tier TEXT NOT NULL DEFAULT 'free' 
        CHECK (subscription_tier IN ('free', 'pro', 'ultra', 'enterprise')),
    display_name TEXT,
    gender TEXT CHECK (gender IN ('male', 'female', 'other', 'prefer_not_to_say')),
    birthday DATE,
    language TEXT NOT NULL DEFAULT 'zh-CN',
    theme TEXT NOT NULL DEFAULT 'system' CHECK (theme IN ('system', 'light', 'dark')),
    email_notifications BOOLEAN NOT NULL DEFAULT true,
    notification_frequency TEXT NOT NULL DEFAULT 'realtime' 
        CHECK (notification_frequency IN ('realtime', 'daily', 'weekly')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================================
-- 用户配额表
-- ============================================
CREATE TABLE IF NOT EXISTS user_quotas (
    user_id UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    monthly_video_limit INTEGER NOT NULL DEFAULT 10,
    monthly_videos_used INTEGER NOT NULL DEFAULT 0 CHECK (monthly_videos_used >= 0),
    total_storage_mb INTEGER NOT NULL DEFAULT 1000,
    used_storage_mb INTEGER NOT NULL DEFAULT 0 CHECK (used_storage_mb >= 0),
    reset_date TIMESTAMP WITH TIME ZONE NOT NULL,
    max_channel_subscriptions INTEGER NOT NULL DEFAULT 3,
    max_video_duration_seconds INTEGER NOT NULL DEFAULT 600,
    api_access_enabled BOOLEAN NOT NULL DEFAULT false,
    priority_processing BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================================
-- 视频相关表
-- ============================================
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    duration REAL,
    source_type TEXT NOT NULL CHECK (source_type IN ('youtube', 'upload', 'youtube_transcript')),
    original_url TEXT,
    oss_video_url TEXT NOT NULL,
    oss_audio_url TEXT,
    video_format TEXT,
    video_size BIGINT,
    video_resolution TEXT,
    processing_status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    processing_progress INTEGER NOT NULL DEFAULT 0 CHECK (processing_progress >= 0 AND processing_progress <= 100),
    error_message TEXT,
    upload_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 视频总结表
CREATE TABLE IF NOT EXISTS video_summaries (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    summary_type TEXT NOT NULL CHECK (summary_type IN ('brief', 'standard', 'detailed')),
    content TEXT NOT NULL,
    model_used TEXT NOT NULL DEFAULT 'qwen3-vl-flash',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 转录记录表
CREATE TABLE IF NOT EXISTS transcripts (
    video_id TEXT PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
    language TEXT NOT NULL DEFAULT 'zh-CN',
    overall_confidence REAL,
    total_segments INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 转录段落表
CREATE TABLE IF NOT EXISTS transcript_segments (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    confidence REAL,
    speaker_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 关键帧表
CREATE TABLE IF NOT EXISTS keyframes (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    frame_id INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    oss_image_url TEXT NOT NULL,
    scene_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================================
-- YouTube 订阅相关表
-- ============================================
CREATE TABLE IF NOT EXISTS youtube_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    channel_avatar TEXT,
    channel_description TEXT,
    subscriber_count TEXT,
    video_count INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_checked_at TIMESTAMP WITH TIME ZONE,
    last_video_id TEXT,
    last_video_published_at TIMESTAMP WITH TIME ZONE,
    check_interval_minutes INTEGER DEFAULT 5,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    UNIQUE(user_id, channel_id)
);

-- 自动分析视频表
CREATE TABLE IF NOT EXISTS auto_analyzed_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL REFERENCES youtube_subscriptions(id) ON DELETE CASCADE,
    video_id TEXT REFERENCES videos(video_id) ON DELETE SET NULL,
    youtube_video_id TEXT NOT NULL,
    youtube_video_title TEXT,
    youtube_video_thumbnail TEXT,
    youtube_video_duration TEXT,
    youtube_video_published_at TIMESTAMP WITH TIME ZONE,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    analysis_status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (analysis_status IN ('pending', 'processing', 'completed', 'failed', 'skipped')),
    analysis_started_at TIMESTAMP WITH TIME ZONE,
    analysis_completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================================
-- Schema 版本控制表
-- ============================================
CREATE TABLE IF NOT EXISTS schema_versions (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    description TEXT
);

-- 插入初始版本记录
INSERT INTO schema_versions (version, description) 
VALUES ('1.0.0', '初始化本地数据库 schema，替代 Supabase')
ON CONFLICT (version) DO NOTHING;

-- ============================================
-- 索引
-- ============================================

-- 用户表索引
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_oauth ON users(oauth_provider, oauth_account_id);

-- OAuth 账号索引
CREATE INDEX IF NOT EXISTS idx_oauth_accounts_user_id ON oauth_accounts(user_id);

-- 视频表索引
CREATE INDEX IF NOT EXISTS idx_videos_user_id ON videos(user_id);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(processing_status);
CREATE INDEX IF NOT EXISTS idx_videos_created_at ON videos(created_at DESC);

-- 视频总结索引
CREATE INDEX IF NOT EXISTS idx_video_summaries_video_id ON video_summaries(video_id);

-- 转录段落索引
CREATE INDEX IF NOT EXISTS idx_transcript_segments_video_id ON transcript_segments(video_id);

-- 关键帧索引
CREATE INDEX IF NOT EXISTS idx_keyframes_video_id ON keyframes(video_id);

-- YouTube 订阅索引
CREATE INDEX IF NOT EXISTS idx_youtube_subscriptions_user_id ON youtube_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_youtube_subscriptions_channel_id ON youtube_subscriptions(channel_id);

-- 自动分析视频索引
CREATE INDEX IF NOT EXISTS idx_auto_analyzed_videos_subscription_id ON auto_analyzed_videos(subscription_id);
CREATE INDEX IF NOT EXISTS idx_auto_analyzed_videos_status ON auto_analyzed_videos(analysis_status);
CREATE INDEX IF NOT EXISTS idx_auto_analyzed_videos_youtube_video_id ON auto_analyzed_videos(youtube_video_id);

-- ============================================
-- 触发器：自动更新 updated_at
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为需要的表添加触发器
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY['users', 'profiles', 'user_quotas', 'videos', 'youtube_subscriptions', 'auto_analyzed_videos'])
    LOOP
        EXECUTE format('
            DROP TRIGGER IF EXISTS update_%I_updated_at ON %I;
            CREATE TRIGGER update_%I_updated_at
                BEFORE UPDATE ON %I
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        ', t, t, t, t);
    END LOOP;
END $$;

-- ============================================
-- 初始化完成
-- ============================================
DO $$
BEGIN
    RAISE NOTICE 'VidSnap 数据库初始化完成!';
END $$;

