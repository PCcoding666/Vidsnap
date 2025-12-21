-- ============================================================================
-- Supabase Schema v3.0 - User Profile & Settings Extension
-- ============================================================================
-- 功能:
--   - 扩展用户资料字段（昵称、性别、生日）
--   - 用户偏好设置（语言、主题、通知）
--   - 订阅等级扩展（添加 ultra 等级）
-- ============================================================================

-- ============================================================================
-- 1. 扩展 profiles 表字段
-- ============================================================================

-- 添加自定义显示名称
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS display_name TEXT;

-- 添加性别字段
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS gender TEXT CHECK (gender IN ('male', 'female', 'other', 'prefer_not_to_say'));

-- 添加生日字段
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS birthday DATE;

-- 添加语言偏好（默认简体中文）
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'zh-CN';

-- 添加主题偏好（system/light/dark）
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS theme TEXT NOT NULL DEFAULT 'system' CHECK (theme IN ('system', 'light', 'dark'));

-- 添加邮件通知开关
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN NOT NULL DEFAULT true;

-- 添加通知频率设置（realtime: 实时, daily: 每日汇总, weekly: 每周汇总）
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS notification_frequency TEXT NOT NULL DEFAULT 'realtime' CHECK (notification_frequency IN ('realtime', 'daily', 'weekly'));

-- 更新订阅等级约束，添加 ultra 等级
ALTER TABLE public.profiles 
DROP CONSTRAINT IF EXISTS profiles_subscription_tier_check;

ALTER TABLE public.profiles 
ADD CONSTRAINT profiles_subscription_tier_check 
CHECK (subscription_tier IN ('free', 'pro', 'ultra', 'enterprise'));

-- ============================================================================
-- 2. 更新 user_quotas 表以支持新的订阅等级
-- ============================================================================

-- 添加频道订阅数限制
ALTER TABLE public.user_quotas 
ADD COLUMN IF NOT EXISTS max_channel_subscriptions INTEGER NOT NULL DEFAULT 3;

-- 添加单视频最大时长限制（秒）
ALTER TABLE public.user_quotas 
ADD COLUMN IF NOT EXISTS max_video_duration_seconds INTEGER NOT NULL DEFAULT 600;

-- 添加 API 访问权限
ALTER TABLE public.user_quotas 
ADD COLUMN IF NOT EXISTS api_access_enabled BOOLEAN NOT NULL DEFAULT false;

-- 添加优先处理权限
ALTER TABLE public.user_quotas 
ADD COLUMN IF NOT EXISTS priority_processing BOOLEAN NOT NULL DEFAULT false;

-- ============================================================================
-- 3. 创建用户设置更新函数
-- ============================================================================

-- 更新用户资料
CREATE OR REPLACE FUNCTION update_user_profile(
    p_user_id UUID,
    p_display_name TEXT DEFAULT NULL,
    p_gender TEXT DEFAULT NULL,
    p_birthday DATE DEFAULT NULL
)
RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    UPDATE public.profiles
    SET 
        display_name = COALESCE(p_display_name, display_name),
        gender = COALESCE(p_gender, gender),
        birthday = COALESCE(p_birthday, birthday),
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING jsonb_build_object(
        'id', id,
        'email', email,
        'display_name', display_name,
        'gender', gender,
        'birthday', birthday,
        'language', language,
        'theme', theme,
        'email_notifications', email_notifications,
        'notification_frequency', notification_frequency,
        'subscription_tier', subscription_tier
    ) INTO v_result;
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 更新用户设置
CREATE OR REPLACE FUNCTION update_user_settings(
    p_user_id UUID,
    p_language TEXT DEFAULT NULL,
    p_theme TEXT DEFAULT NULL,
    p_email_notifications BOOLEAN DEFAULT NULL,
    p_notification_frequency TEXT DEFAULT NULL
)
RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    UPDATE public.profiles
    SET 
        language = COALESCE(p_language, language),
        theme = COALESCE(p_theme, theme),
        email_notifications = COALESCE(p_email_notifications, email_notifications),
        notification_frequency = COALESCE(p_notification_frequency, notification_frequency),
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING jsonb_build_object(
        'language', language,
        'theme', theme,
        'email_notifications', email_notifications,
        'notification_frequency', notification_frequency
    ) INTO v_result;
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- 4. 创建配额配置函数（根据订阅等级设置配额）
-- ============================================================================

CREATE OR REPLACE FUNCTION set_quota_by_tier(p_user_id UUID, p_tier TEXT)
RETURNS VOID AS $$
BEGIN
    -- Free 等级
    IF p_tier = 'free' THEN
        UPDATE public.user_quotas
        SET 
            monthly_video_limit = 5,
            total_storage_mb = 500,
            max_channel_subscriptions = 3,
            max_video_duration_seconds = 600, -- 10分钟
            api_access_enabled = false,
            priority_processing = false
        WHERE user_id = p_user_id;
    
    -- Pro 等级
    ELSIF p_tier = 'pro' THEN
        UPDATE public.user_quotas
        SET 
            monthly_video_limit = 50,
            total_storage_mb = 5120, -- 5GB
            max_channel_subscriptions = 20,
            max_video_duration_seconds = 3600, -- 60分钟
            api_access_enabled = false,
            priority_processing = false
        WHERE user_id = p_user_id;
    
    -- Ultra 等级
    ELSIF p_tier = 'ultra' THEN
        UPDATE public.user_quotas
        SET 
            monthly_video_limit = 200,
            total_storage_mb = 20480, -- 20GB
            max_channel_subscriptions = 100,
            max_video_duration_seconds = 0, -- 无限制
            api_access_enabled = true,
            priority_processing = true
        WHERE user_id = p_user_id;
    
    -- Enterprise 等级
    ELSIF p_tier = 'enterprise' THEN
        UPDATE public.user_quotas
        SET 
            monthly_video_limit = 1000,
            total_storage_mb = 102400, -- 100GB
            max_channel_subscriptions = 500,
            max_video_duration_seconds = 0, -- 无限制
            api_access_enabled = true,
            priority_processing = true
        WHERE user_id = p_user_id;
    END IF;
    
    -- 同时更新 profiles 表的订阅等级
    UPDATE public.profiles
    SET subscription_tier = p_tier, updated_at = NOW()
    WHERE id = p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- 5. 创建索引
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_profiles_language ON public.profiles(language);
CREATE INDEX IF NOT EXISTS idx_profiles_display_name ON public.profiles(display_name);

-- ============================================================================
-- 6. 更新 Schema 版本
-- ============================================================================

INSERT INTO public.schema_versions (version, description)
VALUES ('3.0', '用户资料与设置扩展: display_name, gender, birthday, language, theme, email_notifications')
ON CONFLICT (version) DO UPDATE SET 
    applied_at = NOW(),
    description = EXCLUDED.description;

-- ============================================================================
-- 初始化完成
-- ============================================================================

