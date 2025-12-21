import { useState } from "react";
import { useTranslation } from "react-i18next";
import Header from "@/components/Header";
import LeftPanel from "@/components/app/LeftPanel";
import CenterPanel from "@/components/app/CenterPanel";
import RightPanel from "@/components/app/RightPanel";
import { apiService } from "@/services/api";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";

type ProcessingState = "idle" | "processing" | "completed" | "error" | "no_transcript";

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
  sourceType?: string;  // 新增：标识数据来源 (youtube_transcript / upload)
  language?: string;    // 新增：转录语言
}

const MainApp = () => {
  const { toast } = useToast();
  const { t } = useTranslation();
  const [processingState, setProcessingState] = useState<ProcessingState>("idle");
  const [videoData, setVideoData] = useState<VideoData | null>(null);
  const [currentTimestamp, setCurrentTimestamp] = useState<number>(0);
  const [highlightedKeyframes, setHighlightedKeyframes] = useState<number[]>([]);
  
  // 用于从关键帧传递图片到聊天
  const [selectedKeyframeForChat, setSelectedKeyframeForChat] = useState<{ id: number; url: string } | null>(null);

  const handleStartProcessing = async (input: string | File, type: "youtube" | "upload") => {
    setProcessingState("processing");
    
    try {
      toast({
        title: t('processing.startTitle'),
        description: type === "youtube" ? t('processing.downloadingYoutube') : t('processing.uploadingVideo'),
      });

      const response = await apiService.processVideo({
        youtube_url: type === "youtube" ? (input as string) : undefined,
        video_file: type === "upload" ? (input as File) : undefined,
      });

      if (response.status === "success") {
        console.log("✅ 后端响应数据:", response);
        
        try {
          setProcessingState("completed");
          
          // 转换后端数据格式到前端格式
          const metadata = response.metadata;
          const summary = response.video_summary;
          
          console.log("metadata:", metadata);
          console.log("summary:", summary);
          
          // 处理duration: 从秒数转换为 "M:SS" 格式
          const formatDuration = (seconds: number | string): string => {
            if (typeof seconds === 'string') return seconds;
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return `${mins}:${secs.toString().padStart(2, '0')}`;
          };
          
          // Process summary: prioritize detailed, then standard, then brief
          // 支持新旧两种响应格式
          let summaryText = "";
          if (summary?.detailed_summary) {
            summaryText = summary.detailed_summary;
          } else if (summary?.detailed || summary?.standard || summary?.brief) {
            summaryText = summary?.detailed || summary?.standard || summary?.brief;
          } else if (typeof summary === 'string') {
            summaryText = summary;
          } else {
            summaryText = t('video.noSummaryAvailable');
          }
          
          // 处理transcript: 处理多种可能的数据结构
          let transcriptText = "";
          if (response.transcript) {
            // 新格式：直接在响应顶层
            if (typeof response.transcript === 'string') {
              transcriptText = response.transcript;
            } else if (Array.isArray(response.transcript.segments)) {
              transcriptText = response.transcript.segments.map((seg: any) => seg.text).join(" ");
            } else if (response.transcript.full_text) {
              transcriptText = response.transcript.full_text;
            }
          } else if (metadata?.transcript) {
            // 旧格式：在metadata中
            if (typeof metadata.transcript === 'string') {
              transcriptText = metadata.transcript;
            } else if (Array.isArray(metadata.transcript.segments)) {
              transcriptText = metadata.transcript.segments.map((seg: any) => seg.text).join(" ");
            } else if (metadata.transcript.full_text) {
              transcriptText = metadata.transcript.full_text;
            }
          }
          
          // 关键帧已禁用，返回空数组
          const keyframes: Keyframe[] = [];
          
          const videoData: VideoData = {
            id: response.video_id,
            title: metadata?.video?.title || metadata?.title || t('video.untitled'),
            duration: metadata?.video?.duration ? formatDuration(metadata.video.duration) : (metadata?.duration ? formatDuration(metadata.duration) : t('video.unknownDuration')),
            summary: summaryText,
            keyframes,
            transcript: transcriptText,
            sourceType: response.source_type,
            language: response.language,
          };
          
          console.log("✅ 转换后的视频数据:", videoData);
          setVideoData(videoData);

          toast({
            title: t('processing.completeTitle'),
            description: response.source_type === "youtube_transcript" 
              ? "已使用YouTube字幕完成分析" 
              : "视频分析完成",
          });
        } catch (dataError: any) {
          console.error("Data conversion failed:", dataError);
          throw new Error(t('processing.dataConversionFailed', { message: dataError.message }));
        }
      } else if (response.status === "no_transcript") {
        // 视频没有字幕，需要用户手动下载
        setProcessingState("no_transcript");
        toast({
          variant: "destructive",
          title: "需要手动下载",
          description: response.message || "该视频没有可用字幕，请使用下载工具下载后上传",
        });
      } else {
        throw new Error(t('processing.processingFailed'));
      }
    } catch (error: any) {
      console.error("Video processing failed:", error);
      setProcessingState("error");
      
      toast({
        variant: "destructive",
        title: t('processing.failedTitle'),
        description: error.message || t('processing.failedDescription'),
      });
    }
  };

  const handleTimestampJump = (timestamp: number) => {
    setCurrentTimestamp(timestamp);
  };

  const handleHighlightKeyframes = (frameIds: number[]) => {
    setHighlightedKeyframes(frameIds);
    setTimeout(() => setHighlightedKeyframes([]), 3000);
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
        const metadata = response.metadata;
        const summary = response.video_summary;
        
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
            transcriptText = metadata.transcript.segments.map((seg: any) => seg.text).join(" ");
          } else if (metadata.transcript.full_text) {
            transcriptText = metadata.transcript.full_text;
          }
        }
        
        // Process keyframes
        const keyframes = (metadata?.keyframes || []).map((kf: any, idx: number) => ({
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
    } catch (error: any) {
      console.error("Failed to load history video:", error);
      setProcessingState("error");
      
      toast({
        variant: "destructive",
        title: "❌ Load Failed",
        description: error.message || "Failed to load video details, please try again",
      });
    }
  };

  // 处理示例视频点击
  const handleDemoClick = (demoUrl: string) => {
    handleStartProcessing(demoUrl, "youtube");
  };

  // 处理从关键帧点击"用这张图提问"
  const handleAskWithKeyframe = (frameId: number, frameUrl: string) => {
    setSelectedKeyframeForChat({ id: frameId, url: frameUrl });
    console.log("选中关键帧用于提问:", frameId, frameUrl);
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
            currentTimestamp={currentTimestamp}
            highlightedKeyframes={highlightedKeyframes}
            onTimestampJump={handleTimestampJump}
            onAskWithKeyframe={handleAskWithKeyframe}
            onDemoClick={handleDemoClick}
          />

          {/* Right Panel - Fixed width sidebar */}
          <RightPanel 
            videoData={videoData}
            onTimestampJump={handleTimestampJump}
            onHighlightKeyframes={handleHighlightKeyframes}
            selectedKeyframe={selectedKeyframeForChat}
            onKeyframeUsed={() => setSelectedKeyframeForChat(null)}
          />
        </div>
      </div>
    </div>
  );
};

export default MainApp;