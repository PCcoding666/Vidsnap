import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Clock, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Keyframe } from "@/pages/MainApp";

interface KeyframesGalleryProps {
  keyframes: Keyframe[];
  highlightedKeyframes?: number[];
  onTimestampClick?: (timestamp: number) => void;
  onAskWithKeyframe?: (frameId: number, frameUrl: string) => void;
}

const KeyframesGallery = ({ 
  keyframes, 
  highlightedKeyframes = [],
  onTimestampClick,
  onAskWithKeyframe
}: KeyframesGalleryProps) => {
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${String(secs).padStart(2, '0')}`;
  };

  return (
    <div className="grid grid-cols-3 gap-6">
      {keyframes.map((frame) => {
        const isHighlighted = highlightedKeyframes.includes(frame.id);
        
        return (
          <Card
            key={frame.id}
            className={cn(
              "overflow-hidden hover:shadow-lg transition-all cursor-pointer group",
              isHighlighted && "ring-2 ring-yellow-500 shadow-lg shadow-yellow-500/40 animate-pulse"
            )}
            onClick={() => onTimestampClick?.(frame.timestamp)}
          >
            <div className="aspect-video bg-gradient-to-br from-primary/10 to-accent/10 relative overflow-hidden">
              {frame.url ? (
                <img 
                  src={frame.url} 
                  alt={frame.description}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    // 图片加载失败时的处理
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-4xl opacity-50">🎬</span>
                </div>
              )}
              <div className="absolute bottom-2 right-2 bg-black/70 text-white px-2 py-1 rounded text-xs flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatTime(frame.timestamp)}
              </div>
            </div>
            <div className="p-4">
              <p className="text-sm font-medium group-hover:text-primary transition-colors mb-2">
                帧 #{frame.id}
              </p>
              <p className="text-xs text-muted-foreground mb-3">
                {frame.description}
              </p>
              <Button
                variant="ghost"
                size="sm"
                className="w-full h-7 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  if (onAskWithKeyframe && frame.url) {
                    onAskWithKeyframe(frame.id, frame.url);
                  }
                }}
              >
                <MessageSquare className="w-3 h-3 mr-1" />
                用这张图提问
              </Button>
            </div>
          </Card>
        );
      })}
    </div>
  );
};

export default KeyframesGallery;
