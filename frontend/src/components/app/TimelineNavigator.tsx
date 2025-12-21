import { useState } from "react";
import type { Keyframe } from "@/pages/MainApp";

interface TimelineNavigatorProps {
  keyframes: Keyframe[];
  duration: string;
  currentTimestamp: number;
  onTimestampClick: (timestamp: number) => void;
}

const TimelineNavigator = ({ 
  keyframes, 
  duration, 
  currentTimestamp,
  onTimestampClick 
}: TimelineNavigatorProps) => {
  const [hoveredTimestamp, setHoveredTimestamp] = useState<number | null>(null);
  
  // Parse duration (format: "M:SS") to seconds
  const [minutes, seconds] = duration.split(':').map(Number);
  const totalSeconds = minutes * 60 + seconds;

  const handleBarClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const percentage = clickX / rect.width;
    const timestamp = Math.floor(percentage * totalSeconds);
    onTimestampClick(timestamp);
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${String(secs).padStart(2, '0')}`;
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>时间轴导航</span>
        <span>{keyframes.length} 个关键帧</span>
      </div>

      <div 
        className="relative h-12 rounded-lg overflow-hidden cursor-pointer group"
        onClick={handleBarClick}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const hoverX = e.clientX - rect.left;
          const percentage = hoverX / rect.width;
          setHoveredTimestamp(Math.floor(percentage * totalSeconds));
        }}
        onMouseLeave={() => setHoveredTimestamp(null)}
      >
        {/* Gradient background */}
        <div className="absolute inset-0 bg-gradient-to-r from-primary to-accent opacity-60" />
        
        {/* Keyframe markers */}
        {keyframes.map((frame) => {
          const position = (frame.timestamp / totalSeconds) * 100;
          return (
            <div
              key={frame.id}
              className="absolute top-0 w-0.5 h-full bg-background opacity-60"
              style={{ left: `${position}%` }}
              title={`${formatTime(frame.timestamp)} - ${frame.description}`}
            />
          );
        })}

        {/* Current position indicator */}
        <div
          className="absolute top-0 transition-all duration-300"
          style={{ left: `${(currentTimestamp / totalSeconds) * 100}%` }}
        >
          <div className="relative">
            <div className="w-0 h-0 border-l-[8px] border-l-transparent border-r-[8px] border-r-transparent border-t-[12px] border-t-destructive -translate-x-2" />
            <div className="w-0.5 h-12 bg-destructive -translate-x-[1px]" />
          </div>
        </div>

        {/* Hover preview */}
        {hoveredTimestamp !== null && (
          <div
            className="absolute top-full mt-2 px-2 py-1 bg-popover text-popover-foreground text-xs rounded shadow-lg z-10 pointer-events-none"
            style={{ left: `${(hoveredTimestamp / totalSeconds) * 100}%`, transform: 'translateX(-50%)' }}
          >
            {formatTime(hoveredTimestamp)}
          </div>
        )}
      </div>

      <div className="flex justify-between text-xs text-muted-foreground">
        <span>0:00</span>
        <span className="font-medium">
          当前: {formatTime(currentTimestamp)}
        </span>
        <span>{duration}</span>
      </div>
    </div>
  );
};

export default TimelineNavigator;
