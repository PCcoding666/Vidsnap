export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "13.0.5"
  }
  public: {
    Tables: {
      keyframes: {
        Row: {
          created_at: string
          frame_id: number
          id: number
          oss_image_url: string
          scene_description: string | null
          timestamp: number
          video_id: string
        }
        Insert: {
          created_at?: string
          frame_id: number
          id?: number
          oss_image_url: string
          scene_description?: string | null
          timestamp: number
          video_id: string
        }
        Update: {
          created_at?: string
          frame_id?: number
          id?: number
          oss_image_url?: string
          scene_description?: string | null
          timestamp?: number
          video_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "keyframes_video_id_fkey"
            columns: ["video_id"]
            isOneToOne: false
            referencedRelation: "videos"
            referencedColumns: ["video_id"]
          },
        ]
      }
      profiles: {
        Row: {
          avatar_url: string | null
          created_at: string
          email: string
          full_name: string | null
          id: string
          subscription_tier: string
          updated_at: string
          username: string | null
        }
        Insert: {
          avatar_url?: string | null
          created_at?: string
          email: string
          full_name?: string | null
          id: string
          subscription_tier?: string
          updated_at?: string
          username?: string | null
        }
        Update: {
          avatar_url?: string | null
          created_at?: string
          email?: string
          full_name?: string | null
          id?: string
          subscription_tier?: string
          updated_at?: string
          username?: string | null
        }
        Relationships: []
      }
      schema_versions: {
        Row: {
          applied_at: string
          description: string | null
          version: string
        }
        Insert: {
          applied_at?: string
          description?: string | null
          version: string
        }
        Update: {
          applied_at?: string
          description?: string | null
          version?: string
        }
        Relationships: []
      }
      transcript_segments: {
        Row: {
          confidence: number | null
          created_at: string
          end_time: number
          id: number
          segment_index: number
          speaker_id: string | null
          start_time: number
          text: string
          video_id: string
        }
        Insert: {
          confidence?: number | null
          created_at?: string
          end_time: number
          id?: number
          segment_index: number
          speaker_id?: string | null
          start_time: number
          text: string
          video_id: string
        }
        Update: {
          confidence?: number | null
          created_at?: string
          end_time?: number
          id?: number
          segment_index?: number
          speaker_id?: string | null
          start_time?: number
          text?: string
          video_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "transcript_segments_video_id_fkey"
            columns: ["video_id"]
            isOneToOne: false
            referencedRelation: "videos"
            referencedColumns: ["video_id"]
          },
        ]
      }
      transcripts: {
        Row: {
          created_at: string
          language: string
          overall_confidence: number | null
          total_segments: number
          video_id: string
        }
        Insert: {
          created_at?: string
          language?: string
          overall_confidence?: number | null
          total_segments?: number
          video_id: string
        }
        Update: {
          created_at?: string
          language?: string
          overall_confidence?: number | null
          total_segments?: number
          video_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "transcripts_video_id_fkey"
            columns: ["video_id"]
            isOneToOne: true
            referencedRelation: "videos"
            referencedColumns: ["video_id"]
          },
        ]
      }
      user_quotas: {
        Row: {
          created_at: string
          monthly_video_limit: number
          monthly_videos_used: number
          reset_date: string
          total_storage_mb: number
          updated_at: string
          used_storage_mb: number
          user_id: string
        }
        Insert: {
          created_at?: string
          monthly_video_limit?: number
          monthly_videos_used?: number
          reset_date: string
          total_storage_mb?: number
          updated_at?: string
          used_storage_mb?: number
          user_id: string
        }
        Update: {
          created_at?: string
          monthly_video_limit?: number
          monthly_videos_used?: number
          reset_date?: string
          total_storage_mb?: number
          updated_at?: string
          used_storage_mb?: number
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "user_quotas_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: true
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      video_summaries: {
        Row: {
          content: string
          created_at: string
          id: number
          model_used: string
          summary_type: string
          video_id: string
        }
        Insert: {
          content: string
          created_at?: string
          id?: number
          model_used?: string
          summary_type: string
          video_id: string
        }
        Update: {
          content?: string
          created_at?: string
          id?: number
          model_used?: string
          summary_type?: string
          video_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "video_summaries_video_id_fkey"
            columns: ["video_id"]
            isOneToOne: false
            referencedRelation: "videos"
            referencedColumns: ["video_id"]
          },
        ]
      }
      videos: {
        Row: {
          created_at: string
          duration: number | null
          error_message: string | null
          original_url: string | null
          oss_audio_url: string | null
          oss_video_url: string
          processing_completed_at: string | null
          processing_progress: number
          processing_started_at: string | null
          processing_status: string
          source_type: string
          title: string
          updated_at: string
          upload_time: string
          user_id: string
          video_format: string | null
          video_id: string
          video_resolution: string | null
          video_size: number | null
        }
        Insert: {
          created_at?: string
          duration?: number | null
          error_message?: string | null
          original_url?: string | null
          oss_audio_url?: string | null
          oss_video_url: string
          processing_completed_at?: string | null
          processing_progress?: number
          processing_started_at?: string | null
          processing_status?: string
          source_type: string
          title: string
          updated_at?: string
          upload_time?: string
          user_id: string
          video_format?: string | null
          video_id: string
          video_resolution?: string | null
          video_size?: number | null
        }
        Update: {
          created_at?: string
          duration?: number | null
          error_message?: string | null
          original_url?: string | null
          oss_audio_url?: string | null
          oss_video_url?: string
          processing_completed_at?: string | null
          processing_progress?: number
          processing_started_at?: string | null
          processing_status?: string
          source_type?: string
          title?: string
          updated_at?: string
          upload_time?: string
          user_id?: string
          video_format?: string | null
          video_id?: string
          video_resolution?: string | null
          video_size?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "videos_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      increment_monthly_videos: {
        Args: { p_user_id: string }
        Returns: undefined
      }
      update_storage_usage: {
        Args: { p_size_mb: number; p_user_id: string }
        Returns: undefined
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
