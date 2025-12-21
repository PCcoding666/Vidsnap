import VideoInputPanel from "@/components/dashboard/VideoInputPanel";
import HistoryPanel from "@/components/dashboard/HistoryPanel";

interface LeftPanelProps {
  onStartProcessing: (input: string | File, type: "youtube" | "upload") => void;
  processingState: "idle" | "processing" | "completed" | "error";
  onVideoSelect?: (videoId: string) => void;
}

const LeftPanel = ({ onStartProcessing, processingState, onVideoSelect }: LeftPanelProps) => {
  return (
    <aside className="w-[320px] flex-shrink-0 flex flex-col gap-4">
      {/* 视频输入卡片 */}
      <div className="bg-card rounded-2xl border border-border/60 shadow-sm p-5">
        <VideoInputPanel 
          onStartProcessing={onStartProcessing}
          disabled={processingState === "processing"}
        />
      </div>
      
      {/* 历史记录卡片 */}
      <div className="bg-card rounded-2xl border border-border/60 shadow-sm p-5 flex-1 min-h-0">
        <HistoryPanel onVideoSelect={onVideoSelect} />
      </div>
    </aside>
  );
};

export default LeftPanel;