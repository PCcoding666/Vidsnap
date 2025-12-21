import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Copy, Download, FileDown } from "lucide-react";
import MarkdownRenderer from "@/components/chat/MarkdownRenderer";
import type { VideoData } from "@/pages/MainApp";

interface SummaryViewProps {
  videoData: VideoData;
}

const SummaryView = ({ videoData }: SummaryViewProps) => {
  // 从 summary中提取关键点（如果有的话）
  // TODO: 后续可以让LLM生成结构化的关键点
  const keyPoints = [
    "视频内容的核心要点",
  ];

  return (
    <div className="space-y-6">
      {/* Key Points */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>🎯</span>
          核心观点
        </h3>
        <div className="space-y-3">
          {keyPoints.map((point, index) => (
            <div
              key={index}
              className="flex gap-3 p-4 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
            >
              <span className="text-primary font-semibold">•</span>
              <p className="flex-1">{point}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Detailed Summary */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <span>📚</span>
            详细总结
          </h3>
          <Button 
            variant="ghost" 
            size="sm" 
            className="gap-2"
            onClick={() => {
              navigator.clipboard.writeText(videoData.summary);
            }}
          >
            <Copy className="w-4 h-4" />
            复制
          </Button>
        </div>
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <MarkdownRenderer content={videoData.summary || "暂无总结"} />
        </div>
      </Card>

      {/* Video Info */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>📊</span>
          视频信息
        </h3>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center p-4 rounded-lg bg-muted/50">
            <div className="text-2xl mb-2">🕐</div>
            <p className="text-sm text-muted-foreground mb-1">时长</p>
            <p className="font-semibold">{videoData.duration}</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-muted/50">
            <div className="text-2xl mb-2">👁️</div>
            <p className="text-sm text-muted-foreground mb-1">分辨率</p>
            <p className="font-semibold">1080p</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-muted/50">
            <div className="text-2xl mb-2">💾</div>
            <p className="text-sm text-muted-foreground mb-1">文件大小</p>
            <p className="font-semibold">45.2 MB</p>
          </div>
        </div>
      </Card>

      {/* Actions */}
      <div className="flex gap-4">
        <Button variant="outline" className="flex-1 gap-2">
          <Download className="w-4 h-4" />
          下载原视频
        </Button>
        <Button variant="outline" className="flex-1 gap-2">
          <FileDown className="w-4 h-4" />
          导出总结为 MD
        </Button>
      </div>
    </div>
  );
};

export default SummaryView;
