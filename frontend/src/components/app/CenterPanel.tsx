import ProcessingStatus from "@/components/dashboard/ProcessingStatus";
import TimelineNavigator from "./TimelineNavigator";
import KeyframesGallery from "@/components/dashboard/KeyframesGallery";
import SummaryView from "@/components/dashboard/SummaryView";
import TranscriptViewer from "@/components/dashboard/TranscriptViewer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileText, Image, ScrollText, Play, Cpu, Utensils, Lightbulb } from "lucide-react";
import type { VideoData } from "@/pages/MainApp";

interface CenterPanelProps {
  processingState: "idle" | "processing" | "completed" | "error";
  videoData: VideoData | null;
  currentTimestamp: number;
  highlightedKeyframes: number[];
  onTimestampJump: (timestamp: number) => void;
  onAskWithKeyframe?: (frameId: number, frameUrl: string) => void;
  onDemoClick?: (url: string) => void;
}

// 示例视频数据
const demoVideos = [
  {
    id: "tech",
    title: "Tech Review",
    description: "Product unboxing & analysis",
    url: "https://www.youtube.com/watch?v=example1",
    icon: Cpu,
    gradient: "from-blue-500/10 to-cyan-500/10",
    iconColor: "text-blue-600",
    thumbnail: "https://images.unsplash.com/photo-1518770660439-4636190af475?w=200&h=120&fit=crop",
  },
  {
    id: "cooking",
    title: "Podcast",
    description: "Interview & discussion",
    url: "https://www.youtube.com/watch?v=example2",
    icon: Utensils,
    gradient: "from-orange-500/10 to-red-500/10",
    iconColor: "text-orange-600",
    thumbnail: "https://images.unsplash.com/photo-1478737270239-2f02b77fc618?w=200&h=120&fit=crop",
  },
  {
    id: "ted",
    title: "Tutorial",
    description: "Step-by-step guide",
    url: "https://www.youtube.com/watch?v=example3",
    icon: Lightbulb,
    gradient: "from-purple-500/10 to-pink-500/10",
    iconColor: "text-purple-600",
    thumbnail: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=200&h=120&fit=crop",
  },
];

const CenterPanel = ({ 
  processingState, 
  videoData, 
  currentTimestamp,
  highlightedKeyframes,
  onTimestampJump,
  onAskWithKeyframe,
  onDemoClick
}: CenterPanelProps) => {
  return (
    <main className="flex-1 min-w-0">
      <div className="h-full bg-card rounded-2xl border border-border/60 shadow-sm p-6 overflow-y-auto">
        {processingState === "idle" && (
          <div className="flex flex-col items-center justify-center h-full">
            <div className="text-center space-y-8 max-w-md">
              {/* 主图标 - 更小 */}
              <div className="relative mx-auto w-16 h-16">
                <div className="absolute inset-0 bg-gradient-to-br from-primary/20 to-accent/20 rounded-2xl animate-pulse" />
                <div className="absolute inset-1.5 bg-gradient-to-br from-primary to-accent rounded-xl flex items-center justify-center">
                  <Play className="w-7 h-7 text-primary-foreground ml-0.5" />
                </div>
              </div>
              
              {/* 标题和描述 */}
              <div className="space-y-2">
                <h2 className="text-xl font-semibold text-foreground">Start Analyzing</h2>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Paste a YouTube URL or upload a video file to get AI-powered insights, summaries, and transcripts.
                </p>
              </div>
              
              {/* 示例视频卡片 */}
              <div className="pt-4">
                <p className="text-xs font-medium text-muted-foreground mb-4 uppercase tracking-wide">Or try a sample</p>
                <div className="grid grid-cols-3 gap-3">
                  {demoVideos.map((demo) => (
                    <button
                      key={demo.id}
                      onClick={() => onDemoClick?.(demo.url)}
                      className="group relative overflow-hidden rounded-xl border border-border/60 bg-card hover:border-primary/40 hover:shadow-md transition-all duration-200 text-left"
                    >
                      {/* Thumbnail */}
                      <div className={`aspect-[4/3] bg-gradient-to-br ${demo.gradient} flex items-center justify-center relative overflow-hidden`}>
                        <demo.icon className={`w-8 h-8 ${demo.iconColor} group-hover:scale-110 transition-transform duration-200`} />
                      </div>
                      {/* Label */}
                      <div className="p-2.5">
                        <p className="font-medium text-xs text-foreground">{demo.title}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">{demo.description}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {processingState === "processing" && (
          <ProcessingStatus />
        )}

        {processingState === "completed" && videoData && (
          <div className="space-y-6">
            <TimelineNavigator 
              keyframes={videoData.keyframes}
              duration={videoData.duration}
              currentTimestamp={currentTimestamp}
              onTimestampClick={onTimestampJump}
            />
            
            <Tabs defaultValue="keyframes" className="w-full">
              <TabsList className="grid w-full grid-cols-3 mb-6 bg-muted/50 p-1 rounded-xl">
                <TabsTrigger value="keyframes" className="gap-2 rounded-lg data-[state=active]:bg-card data-[state=active]:shadow-sm">
                  <Image className="w-4 h-4" />
                  Keyframes
                </TabsTrigger>
                <TabsTrigger value="summary" className="gap-2 rounded-lg data-[state=active]:bg-card data-[state=active]:shadow-sm">
                  <FileText className="w-4 h-4" />
                  Summary
                </TabsTrigger>
                <TabsTrigger value="transcript" className="gap-2 rounded-lg data-[state=active]:bg-card data-[state=active]:shadow-sm">
                  <ScrollText className="w-4 h-4" />
                  Transcript
                </TabsTrigger>
              </TabsList>

              <TabsContent value="keyframes">
                <KeyframesGallery 
                  keyframes={videoData.keyframes}
                  highlightedKeyframes={highlightedKeyframes}
                  onTimestampClick={onTimestampJump}
                  onAskWithKeyframe={onAskWithKeyframe}
                />
              </TabsContent>

              <TabsContent value="summary">
                <SummaryView videoData={videoData} />
              </TabsContent>

              <TabsContent value="transcript">
                <TranscriptViewer transcript={videoData.transcript} />
              </TabsContent>
            </Tabs>
          </div>
        )}
        
        {processingState === "error" && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center space-y-4 max-w-md">
              <div className="w-16 h-16 mx-auto rounded-2xl bg-destructive/10 flex items-center justify-center">
                <span className="text-3xl">❌</span>
              </div>
              <h2 className="text-lg font-semibold text-destructive">Processing Failed</h2>
              <p className="text-sm text-muted-foreground">
                Something went wrong while processing your video. Please check the URL or file and try again.
              </p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
};

export default CenterPanel;