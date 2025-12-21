import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Clock, PlayCircle, Loader2, RefreshCw, AlertCircle } from "lucide-react";
import { apiService, type VideoHistoryItem } from "@/services/api";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";

interface HistoryPanelProps {
  onVideoSelect?: (videoId: string) => void;
}

const HistoryPanel = ({ onVideoSelect }: HistoryPanelProps = {}) => {
  const { toast } = useToast();
  const { t } = useTranslation();
  const { user } = useAuth();
  const [videos, setVideos] = useState<VideoHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
  }, [user]);

  const loadHistory = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await apiService.getVideoHistory(10);
      
      if (response.status === "success") {
        setVideos(response.videos || []);
        
        if (response.message && response.videos.length === 0) {
          setError(response.message);
        }
      }
    } catch (err) {
      console.error("加载历史记录失败:", err);
      setError("Unable to load");
    } finally {
      setIsLoading(false);
    }
  };

  const formatDuration = (seconds?: number): string => {
    if (!seconds) return "--:--";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTime = (isoString: string): string => {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const handleVideoClick = async (video: VideoHistoryItem) => {
    if (video.processing_status !== 'completed') {
      toast({
        variant: "default",
        title: "Video not ready",
        description: video.processing_status === 'processing' ? t('status.processing') : t('status.failed'),
      });
      return;
    }

    if (onVideoSelect) {
      onVideoSelect(video.id);
    }
  };

  const getStatusDot = (status: string) => {
    const colors: Record<string, string> = {
      completed: "bg-green-500",
      processing: "bg-blue-500 animate-pulse",
      pending: "bg-yellow-500",
      failed: "bg-red-500",
    };
    return colors[status] || colors.pending;
  };

  return (
    <div className="space-y-3 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-muted-foreground" />
          <h3 className="text-sm font-medium text-foreground">Recent</h3>
        </div>
        {error && !isLoading && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 hover:bg-primary/10"
            onClick={loadHistory}
          >
            <RefreshCw className="w-3 h-3" />
          </Button>
        )}
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            <span className="text-xs">Loading...</span>
          </div>
        ) : error && videos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <AlertCircle className="w-5 h-5 text-muted-foreground/50 mb-2" />
            <span className="text-xs text-muted-foreground">{error}</span>
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 h-7 text-xs"
              onClick={loadHistory}
            >
              <RefreshCw className="w-3 h-3 mr-1" />
              Retry
            </Button>
          </div>
        ) : videos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <PlayCircle className="w-5 h-5 text-muted-foreground/50 mb-2" />
            <span className="text-xs text-muted-foreground">No videos yet</span>
          </div>
        ) : (
          <div className="space-y-1.5">
            {videos.map((video) => (
              <button
                key={video.id}
                onClick={() => handleVideoClick(video)}
                className="w-full p-2.5 rounded-lg hover:bg-muted/50 transition-colors text-left group"
              >
                <div className="flex items-start gap-2.5">
                  <div className="relative mt-1">
                    <PlayCircle className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
                    <div className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full ${getStatusDot(video.processing_status)}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                      {video.title}
                    </p>
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground mt-0.5">
                      <span>{formatTime(video.created_at)}</span>
                      <span>·</span>
                      <span>{formatDuration(video.duration)}</span>
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </ScrollArea>

      {videos.length > 0 && (
        <Button 
          variant="ghost" 
          className="w-full text-xs h-8 text-muted-foreground hover:text-foreground hover:bg-muted/50" 
          size="sm"
        >
          View all
        </Button>
      )}
    </div>
  );
};

export default HistoryPanel;