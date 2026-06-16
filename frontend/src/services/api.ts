/**
 * 后端 API 服务配置
 * 提供与 FastAPI 后端的通信接口
 */

// API 基础配置
// 开发环境使用 /api/v1 前缀触发 Vite 代理
const API_BASE_URL = import.meta.env.DEV ? '/api/v1' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');

// API 客户端类
class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    // 从 localStorage 获取 token
    this.token = localStorage.getItem('access_token');
  }

  /**
   * 设置认证 token
   */
  setToken(token: string) {
    this.token = token;
    localStorage.setItem('access_token', token);
  }

  /**
   * 清除认证 token
   */
  clearToken() {
    this.token = null;
    localStorage.removeItem('access_token');
  }

  /**
   * 通用请求方法
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    // 添加认证 token
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('API 请求失败:', error);
      throw error;
    }
  }

  /**
   * GET 请求
   */
  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  /**
   * POST 请求
   */
  async post<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * POST 表单数据
   */
  async postFormData<T>(endpoint: string, formData: FormData): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const headers: HeadersInit = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('API 请求失败:', error);
      throw error;
    }
  }

  /**
   * DELETE 请求
   */
  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  /**
   * PUT 请求
   */
  async put<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }
}

// 创建 API 客户端实例
export const apiClient = new ApiClient(API_BASE_URL);

// API 端点定义
export const API_ENDPOINTS = {
  // 健康检查
  HEALTH: '/health',
  
  // 认证相关
  AUTH: {
    SIGNUP: '/auth/signup',
    SIGNIN: '/auth/signin',
    GOOGLE_LOGIN: '/auth/google/login',
    GOOGLE_CALLBACK: '/auth/google/callback',
  },
  
  // 视频处理
  VIDEO: {
    PROCESS: '/video/process',
    STATUS: '/video/status',
    HISTORY: '/video/history',
    DETAILS: '/video/details',
  },

  // Query-first 工作区
  WORKSPACE: {
    SKILLS: '/workspace/skills',
    PLAN: '/workspace/plan',
    PROCESS: '/workspace/process',
    JOBS: '/workspace/jobs',
    TRANSCRIPTION_PROVIDERS: '/workspace/transcription-providers',
    PLANNER_EVALS: '/workspace/evals/planner',
  },
  
  // 分析结果
  ANALYSIS: {
    GET: '/analysis',
    CHAT_START: '/analysis/chat/start',
    CHAT_MESSAGE: '/analysis/chat/message',
    CHAT_SESSION: '/analysis/chat/session',
  },
  
  // 用户中心
  USER: {
    PROFILE: '/user/profile',
    SETTINGS: '/user/settings',
    QUOTA: '/user/quota',
    STATS: '/user/stats',
  },
} as const;

// 类型定义
export interface HealthCheckResponse {
  status: string;
}

export interface ServiceStatusResponse {
  status: string;
  services: Record<string, boolean>;
}

export interface SignUpRequest {
  email: string;
  password: string;
  username?: string;
}

export interface SignInRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  user: {
    id: string;
    email: string;
    username?: string;
    subscription_tier?: string;
  };
  access_token: string;
  refresh_token: string;
}

export interface ProcessVideoRequest {
  video_file: File;
}

export interface ProcessVideoResponse {
  status: string;
  video_id: string;
  keyframes_count?: number;
  transcript_segments_count?: number;
  metadata?: unknown;
  video_summary?: unknown;
  summary_generated?: boolean;
  source_type?: string;
  language?: string;
  transcript?: string | { segments?: Array<{ text: string }>; full_text?: string };
  message?: string;
}

export type ArtifactType = 'transcript' | 'summary' | 'notes' | 'content_locations' | 'qa_answer';

export interface WorkspacePlanStep {
  id: string;
  skill: string;
  depends_on: string[];
  purpose: string;
  inputs?: Record<string, unknown>;
}

export interface WorkspacePlan {
  plan_id: string;
  query: string;
  artifact_type: ArtifactType;
  steps: WorkspacePlanStep[];
  requires_user_confirmation: boolean;
  cost_tier: 'low' | 'medium' | 'high';
  assumptions: string[];
  rejected_capabilities: string[];
}

export interface WorkspaceArtifact {
  artifact_id: string;
  artifact_type: ArtifactType;
  title: string;
  content: string;
  format: 'markdown' | 'text' | 'json';
  citations: Array<{
    segment_index?: number;
    start_time: number;
    end_time: number;
    text: string;
  }>;
  metadata?: Record<string, unknown>;
}

export interface WorkspaceSkillTrace {
  step_id: string;
  skill: string;
  status: 'planned' | 'running' | 'success' | 'skipped' | 'failed';
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  output_summary?: string;
  error?: string;
}

export interface WorkspaceVideoAsset {
  video_id: string;
  title: string;
  duration: number;
  source_type: 'upload';
  processing_status: string;
  transcript_segments_count: number;
  summary_generated: boolean;
  metadata: Record<string, unknown>;
}

export interface WorkspaceValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface WorkspaceProcessRequest {
  video_file: File;
  query: string;
}

export interface WorkspaceProcessResponse {
  status: string;
  video_asset: WorkspaceVideoAsset;
  plan: WorkspacePlan;
  validation: WorkspaceValidation;
  artifact: WorkspaceArtifact;
  transcript_index: Array<{
    segment_index: number;
    text: string;
    start_time: number;
    end_time: number;
    confidence: number;
  }>;
  skill_trace: WorkspaceSkillTrace[];
}

export type WorkspaceJobStatusValue = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled';

export interface WorkspaceCostEstimate {
  source_file_bytes: number;
  source_file_mb: number;
  source_duration_seconds?: number | null;
  estimated_audio_mb: number;
  estimated_transcript_minutes: number;
  provider: string;
  estimated_audio_format: string;
  chunking_expected: boolean;
  chunk_seconds: number;
  estimated_chunks: number;
  estimate_source: 'media_duration' | 'file_size_fallback';
}

export interface WorkspaceJobStatus {
  job_id: string;
  status: WorkspaceJobStatusValue;
  stage: string;
  progress: number;
  message: string;
  query: string;
  original_filename: string;
  created_at: string;
  updated_at: string;
  attempts: number;
  max_attempts: number;
  retryable: boolean;
  failed_stage?: string | null;
  error?: string | null;
  plan: WorkspacePlan;
  validation: WorkspaceValidation;
  skill_trace: WorkspaceSkillTrace[];
  cost_estimate: WorkspaceCostEstimate;
  artifact_available: boolean;
  artifact_versions_count: number;
  transcript_segments_count: number;
  partial: boolean;
}

export interface WorkspaceJobCreateResponse {
  status: string;
  job_id: string;
  job: WorkspaceJobStatus;
}

export interface WorkspaceJobStatusResponse {
  status: string;
  job: WorkspaceJobStatus;
}

export interface WorkspaceArtifactVersion {
  version: number;
  artifact: WorkspaceArtifact;
  query: string;
  plan_id: string;
  created_at: string;
}

export interface WorkspaceJobArtifactResponse extends WorkspaceProcessResponse {
  job_id: string;
  artifact_versions: WorkspaceArtifactVersion[];
}

export interface WorkspaceQAResponse {
  status: string;
  job_id: string;
  partial: boolean;
  answer: string;
  citations: Array<{
    segment_index?: number;
    start_time: number;
    end_time: number;
    text: string;
  }>;
}

// Chat API 类型定义
export interface ChatStartRequest {
  video_id: string;
  metadata?: unknown;  // 可选，如果不提供，后端会自动从Supabase加载
}

export interface ChatStartResponse {
  status: string;
  session_id: string;
  video_id: string;
  keyframes_count: number;
  transcript_segments_count: number;
}

export interface ChatMessageRequest {
  session_id: string;
  question: string;
  keyframe_ids?: number[];
  top_k?: number;
  auto_keyframes?: boolean;
}

export interface ChatMessageResponse {
  status: string;
  session_id: string;
  answer: string;
  references?: {
    time_ranges?: Array<{
      start_time: number;
      end_time: number;
      text: string;
    }>;
    keyframe_ids?: number[];
    keyframes?: unknown[];
  };
  history_length: number;
}

// 视频历史记录类型
export interface VideoHistoryItem {
  id: string;
  title: string;
  duration?: number;
  created_at: string;
  processing_status: 'pending' | 'processing' | 'completed' | 'failed';
  source_type: 'upload';
  thumbnail_url?: string;
}

export interface VideoHistoryResponse {
  status: string;
  videos: VideoHistoryItem[];
  total: number;
  message?: string;
}

// API 服务方法
export const apiService = {
  // 健康检查
  async healthCheck(): Promise<HealthCheckResponse> {
    return apiClient.get<HealthCheckResponse>(API_ENDPOINTS.HEALTH);
  },

  // 服务状态
  async getServiceStatus(): Promise<ServiceStatusResponse> {
    return apiClient.get<ServiceStatusResponse>(API_ENDPOINTS.VIDEO.STATUS);
  },

  // 用户注册
  async signUp(data: SignUpRequest): Promise<AuthResponse> {
    return apiClient.post<AuthResponse>(API_ENDPOINTS.AUTH.SIGNUP, data);
  },

  // 用户登录
  async signIn(data: SignInRequest): Promise<AuthResponse> {
    const response = await apiClient.post<AuthResponse>(API_ENDPOINTS.AUTH.SIGNIN, data);
    // 保存 token
    apiClient.setToken(response.access_token);
    return response;
  },

  // 处理上传视频
  async processVideo(data: ProcessVideoRequest): Promise<ProcessVideoResponse> {
    const formData = new FormData();
    formData.append('video_file', data.video_file);
    
    return apiClient.postFormData<ProcessVideoResponse>(
      API_ENDPOINTS.VIDEO.PROCESS,
      formData
    );
  },

  // Query-first workspace 处理
  async processWorkspaceQuery(data: WorkspaceProcessRequest): Promise<WorkspaceProcessResponse> {
    const formData = new FormData();
    formData.append('video_file', data.video_file);
    formData.append('query', data.query);

    return apiClient.postFormData<WorkspaceProcessResponse>(
      API_ENDPOINTS.WORKSPACE.PROCESS,
      formData
    );
  },

  async createWorkspaceJob(data: WorkspaceProcessRequest): Promise<WorkspaceJobCreateResponse> {
    const formData = new FormData();
    formData.append('video_file', data.video_file);
    formData.append('query', data.query);

    return apiClient.postFormData<WorkspaceJobCreateResponse>(
      API_ENDPOINTS.WORKSPACE.JOBS,
      formData
    );
  },

  async getWorkspaceJob(jobId: string): Promise<WorkspaceJobStatusResponse> {
    return apiClient.get<WorkspaceJobStatusResponse>(
      `${API_ENDPOINTS.WORKSPACE.JOBS}/${jobId}`
    );
  },

  async getWorkspaceJobArtifact(jobId: string): Promise<WorkspaceJobArtifactResponse> {
    return apiClient.get<WorkspaceJobArtifactResponse>(
      `${API_ENDPOINTS.WORKSPACE.JOBS}/${jobId}/artifact`
    );
  },

  async retryWorkspaceJob(jobId: string): Promise<WorkspaceJobStatusResponse> {
    return apiClient.post<WorkspaceJobStatusResponse>(
      `${API_ENDPOINTS.WORKSPACE.JOBS}/${jobId}/retry`
    );
  },

  async askWorkspaceJob(jobId: string, question: string, top_k = 5): Promise<WorkspaceQAResponse> {
    return apiClient.post<WorkspaceQAResponse>(
      `${API_ENDPOINTS.WORKSPACE.JOBS}/${jobId}/qa`,
      { question, top_k }
    );
  },

  async planWorkspaceQuery(query: string): Promise<{ status: string; plan: WorkspacePlan; validation: WorkspaceValidation }> {
    return apiClient.post(API_ENDPOINTS.WORKSPACE.PLAN, { query });
  },

  // 退出登录
  logout() {
    apiClient.clearToken();
  },

  // 启动聊天会话
  async startChatSession(data: ChatStartRequest): Promise<ChatStartResponse> {
    return apiClient.post<ChatStartResponse>(
      API_ENDPOINTS.ANALYSIS.CHAT_START,
      data
    );
  },

  // 发送聊天消息
  async sendChatMessage(data: ChatMessageRequest): Promise<ChatMessageResponse> {
    return apiClient.post<ChatMessageResponse>(
      API_ENDPOINTS.ANALYSIS.CHAT_MESSAGE,
      data
    );
  },

  // 获取视频历史记录
  async getVideoHistory(limit: number = 20): Promise<VideoHistoryResponse> {
    return apiClient.get<VideoHistoryResponse>(
      `${API_ENDPOINTS.VIDEO.HISTORY}?limit=${limit}`
    );
  },

  // 获取视频详情
  async getVideoDetails(video_id: string): Promise<ProcessVideoResponse> {
    return apiClient.get<ProcessVideoResponse>(
      `${API_ENDPOINTS.VIDEO.DETAILS}/${video_id}`
    );
  },

  // ========================================================================
  // 用户中心方法
  // ========================================================================

  // 获取用户资料
  async getUserProfile(): Promise<unknown> {
    return apiClient.get<unknown>(API_ENDPOINTS.USER.PROFILE);
  },

  // 更新用户资料
  async updateUserProfile(data: {
    display_name?: string;
    gender?: 'male' | 'female' | 'other' | 'prefer_not_to_say';
    birthday?: string;
  }): Promise<unknown> {
    return apiClient.put<unknown>(API_ENDPOINTS.USER.PROFILE, data);
  },

  // 获取用户设置
  async getUserSettings(): Promise<unknown> {
    return apiClient.get<unknown>(API_ENDPOINTS.USER.SETTINGS);
  },

  // 更新用户设置
  async updateUserSettings(data: {
    language?: string;
    theme?: 'system' | 'light' | 'dark';
  }): Promise<unknown> {
    return apiClient.put<unknown>(API_ENDPOINTS.USER.SETTINGS, data);
  },

  // 获取用户配额
  async getUserQuota(): Promise<unknown> {
    return apiClient.get<unknown>(API_ENDPOINTS.USER.QUOTA);
  },

  // 获取用户统计
  async getUserStats(): Promise<unknown> {
    return apiClient.get<unknown>(API_ENDPOINTS.USER.STATS);
  },
};
