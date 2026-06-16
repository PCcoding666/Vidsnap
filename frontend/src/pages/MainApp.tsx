import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Header from "@/components/Header";
import LeftPanel from "@/components/app/LeftPanel";
import CenterPanel from "@/components/app/CenterPanel";
import RightPanel from "@/components/app/RightPanel";
import {
  apiService,
  type WorkspaceJobArtifactResponse,
  type WorkspaceJobStatus,
  type WorkspaceArtifact,
  type WorkspacePlan,
  type WorkspaceSkillTrace,
} from "@/services/api";
import { useToast } from "@/hooks/use-toast";

type ProcessingState = "idle" | "processing" | "completed" | "error";

export interface Keyframe {
  id: number;
  timestamp: number;
  description: string;
  url?: string;
}

export interface VideoData {
  id: string;
  title: string;
  duration: string;
  summary: string;
  keyframes: Keyframe[];  // 保留接口兼容性，但实际会是空数组
  transcript: string;
  sourceType?: string;  // 标识数据来源，目前仅为 upload
  language?: string;    // 新增：转录语言
  userQuery?: string;
  workspaceJobId?: string;
  artifact?: WorkspaceArtifact;
  plan?: WorkspacePlan;
  skillTrace?: WorkspaceSkillTrace[];
}

type TranscriptLike =
  | string
  | {
      segments?: Array<{ text?: string }>;
      full_text?: string;
      language?: string;
    };

type MetadataLike = {
  video?: { title?: string; duration?: number };
  title?: string;
  duration?: number;
  transcript?: TranscriptLike;
  keyframes?: Array<{
    frame_id?: number;
    timestamp?: number;
    scene_description?: string;
    description?: string;
    oss_image_url?: string;
  }>;
};

type SummaryLike = {
  detailed_summary?: string;
  detailed?: string;
  standard?: string;
  brief?: string;
};

const getErrorMessage = (error: unknown) => {
  return error instanceof Error ? error.message : String(error);
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

const formatDuration = (seconds: number | string): string => {
  if (typeof seconds === 'string') return seconds;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const toVideoData = (
  response: WorkspaceJobArtifactResponse,
  query: string,
): VideoData => {
  const metadata = (response.video_asset.metadata || {}) as MetadataLike;
  const transcriptText = response.transcript_index
    .map((seg) => `[${Math.floor(seg.start_time / 60)}:${String(Math.floor(seg.start_time % 60)).padStart(2, "0")}] ${seg.text}`)
    .join("\n");

  return {
    id: response.video_asset.video_id,
    title: response.video_asset.title || metadata?.title || "Untitled Video",
    duration: formatDuration(response.video_asset.duration || metadata?.duration || 0),
    summary: response.artifact.content,
    keyframes: [],
    transcript: transcriptText,
    sourceType: response.video_asset.source_type,
    language: typeof metadata.transcript === "object" ? metadata.transcript.language : undefined,
    userQuery: query,
    workspaceJobId: response.job_id,
    artifact: response.artifact,
    plan: response.plan,
    skillTrace: response.skill_trace,
  };
};

const MainApp = () => {
  const { toast } = useToast();
  const { t } = useTranslation();
  const [processingState, setProcessingState] = useState<ProcessingState>("idle");
  const [videoData, setVideoData] = useState<VideoData | null>(null);
  const [workspaceJob, setWorkspaceJob] = useState<WorkspaceJobStatus | null>(null);
  const [currentTimestamp, setCurrentTimestamp] = useState<number>(0);
  const activeJobRef = useRef<string | null>(null);

  const pollWorkspaceJob = async (jobId: string, query: string) => {
    while (activeJobRef.current === jobId) {
      await sleep(1500);
      const statusResponse = await apiService.getWorkspaceJob(jobId);
      setWorkspaceJob(statusResponse.job);

      if (statusResponse.job.status === "succeeded") {
        const artifactResponse = await apiService.getWorkspaceJobArtifact(jobId);
        const nextVideoData = toVideoData(artifactResponse, query);
        setVideoData(nextVideoData);
        setProcessingState("completed");
        toast({
          title: t('processing.completeTitle'),
          description: `Created ${artifactResponse.artifact.artifact_type} artifact`,
        });
        return;
      }

      if (statusResponse.job.status === "failed") {
        setProcessingState("error");
        toast({
          variant: "destructive",
          title: t('processing.failedTitle'),
          description: statusResponse.job.error || statusResponse.job.message,
        });
        return;
      }
    }
  };

  const handleStartProcessing = async (file: File, query: string) => {
    setProcessingState("processing");
    setVideoData(null);
    setWorkspaceJob(null);
    
    try {
      toast({
        title: t('processing.startTitle'),
        description: "Creating a recoverable workspace job.",
      });

      const createResponse = await apiService.createWorkspaceJob({
        video_file: file,
        query,
      });

      activeJobRef.current = createResponse.job_id;
      setWorkspaceJob(createResponse.job);

      toast({
        title: "Job accepted",
        description: `Tracking ${createResponse.job_id}`,
      });

      await pollWorkspaceJob(createResponse.job_id, query);
    } catch (error: unknown) {
      const message = getErrorMessage(error);
      console.error("Video processing failed:", error);
      setProcessingState("error");
      
      toast({
        variant: "destructive",
        title: t('processing.failedTitle'),
        description: message || t('processing.failedDescription'),
      });
    }
  };

  const handleRetryJob = async (jobId: string) => {
    try {
      const response = await apiService.retryWorkspaceJob(jobId);
      activeJobRef.current = jobId;
      setWorkspaceJob(response.job);
      setProcessingState("processing");
      toast({
        title: "Retry queued",
        description: "Continuing from the saved upload.",
      });
      await pollWorkspaceJob(jobId, response.job.query);
    } catch (error: unknown) {
      const message = getErrorMessage(error);
      setProcessingState("error");
      toast({
        variant: "destructive",
        title: "Retry failed",
        description: message,
      });
    }
  };

  const handleTimestampJump = (timestamp: number) => {
    setCurrentTimestamp(timestamp);
  };

  // Load history video details
  const handleLoadHistoryVideo = async (videoId: string) => {
    setProcessingState("processing");
    
    try {
      toast({
        title: "Loading History",
        description: "Loading video details...",
      });

      const response = await apiService.getVideoDetails(videoId);

      if (response.status === "success") {
        console.log("✅ 加载历史视频数据:", response);
        
        setProcessingState("completed");
        
        // 转换后端数据格式到前端格式
        const metadata = (response.metadata || {}) as MetadataLike;
        const summary = (response.video_summary || {}) as SummaryLike;
        
        // Process duration: convert seconds to "M:SS" format
        const formatDuration = (seconds: number | string): string => {
          if (typeof seconds === 'string') return seconds;
          const mins = Math.floor(seconds / 60);
          const secs = seconds % 60;
          return `${mins}:${secs.toString().padStart(2, '0')}`;
        };
        
        // Process summary: prioritize detailed, then standard, then brief
        const summaryText = summary?.detailed || summary?.standard || summary?.brief || "No summary available";
        
        // Process transcript
        let transcriptText = "";
        if (metadata?.transcript) {
          if (typeof metadata.transcript === 'string') {
            transcriptText = metadata.transcript;
          } else if (Array.isArray(metadata.transcript.segments)) {
            transcriptText = metadata.transcript.segments.map((seg) => seg.text || "").join(" ");
          } else if (metadata.transcript.full_text) {
            transcriptText = metadata.transcript.full_text;
          }
        }
        
        // Process keyframes
        const keyframes = (metadata.keyframes || []).map((kf, idx: number) => ({
          id: kf.frame_id || idx + 1,
          timestamp: kf.timestamp,
          description: kf.scene_description || kf.description || `Keyframe ${idx + 1}`,
          url: kf.oss_image_url,
        }));
        
        const videoData = {
          id: response.video_id,
          title: metadata?.video?.title || metadata?.title || "Untitled Video",
          duration: metadata?.video?.duration ? formatDuration(metadata.video.duration) : (metadata?.duration ? formatDuration(metadata.duration) : "Unknown"),
          summary: summaryText,
          keyframes,
          transcript: transcriptText,
        };
        
        console.log("✅ 转换后的视频数据:", videoData);
        setVideoData(videoData);

        toast({
          title: "✅ Load Successful",
          description: `Loaded video: ${videoData.title}`,
        });
      } else {
        throw new Error("Load failed");
      }
    } catch (error: unknown) {
      const message = getErrorMessage(error);
      console.error("Failed to load history video:", error);
      setProcessingState("error");
      
      toast({
        variant: "destructive",
        title: "❌ Load Failed",
        description: message || "Failed to load video details, please try again",
      });
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-background">
      <Header />
      
      {/* 主应用内容区域 */}
      <div className="pt-16 h-screen flex flex-col">
        <div className="flex flex-1 w-full gap-5 p-5">
          {/* Left Panel - Fixed width sidebar */}
          <LeftPanel 
            onStartProcessing={handleStartProcessing}
            processingState={processingState}
            onVideoSelect={handleLoadHistoryVideo}
          />

          {/* Center Panel - Flexible main content */}
          <CenterPanel 
            processingState={processingState}
            videoData={videoData}
            workspaceJob={workspaceJob}
            currentTimestamp={currentTimestamp}
            onTimestampJump={handleTimestampJump}
            onRetryJob={handleRetryJob}
          />

          {/* Right Panel - Fixed width sidebar */}
          <RightPanel 
            videoData={videoData}
            workspaceJob={workspaceJob}
            onTimestampJump={handleTimestampJump}
            onHighlightKeyframes={() => undefined}
          />
        </div>
      </div>
    </div>
  );
};

export default MainApp;
