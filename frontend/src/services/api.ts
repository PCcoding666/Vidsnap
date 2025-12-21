/**
 * 后端 API 服务配置
 * 提供与 FastAPI 后端的通信接口
 */

// API 基础配置
// 开发环境使用 /api 前缀触发 Vite 代理
const API_BASE_URL = import.meta.env.DEV ? '/api' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');

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
  async post<T>(endpoint: string, data?: any): Promise<T> {
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
    DETAILS: '/video/details',  // 新增视频详情接口
  },
  
  // 分析结果
  ANALYSIS: {
    GET: '/analysis',
    CHAT_START: '/analysis/chat/start',
    CHAT_MESSAGE: '/analysis/chat/message',
    CHAT_SESSION: '/analysis/chat/session',
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
  youtube_url?: string;
  video_file?: File;
}

export interface ProcessVideoResponse {
  status: string;
  video_id: string;
  keyframes_count?: number;
  transcript_segments_count?: number;
  metadata?: any;
  video_summary?: any;
  summary_generated?: boolean;
}

// Chat API 类型定义
export interface ChatStartRequest {
  video_id: string;
  metadata?: any;  // 可选，如果不提供，后端会自动从Supabase加载
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
    keyframes?: any[];
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
  source_type: 'upload' | 'youtube';
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

  // 处理视频
  async processVideo(data: ProcessVideoRequest): Promise<ProcessVideoResponse> {
    const formData = new FormData();
    
    if (data.youtube_url) {
      formData.append('youtube_url', data.youtube_url);
    }
    
    if (data.video_file) {
      formData.append('video_file', data.video_file);
    }
    
    return apiClient.postFormData<ProcessVideoResponse>(
      API_ENDPOINTS.VIDEO.PROCESS,
      formData
    );
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
};
