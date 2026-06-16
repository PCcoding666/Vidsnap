import ProcessingStatus from "@/components/dashboard/ProcessingStatus";
import TimelineNavigator from "./TimelineNavigator";
import SummaryView from "@/components/dashboard/SummaryView";
import TranscriptViewer from "@/components/dashboard/TranscriptViewer";
import ArtifactWorkspace from "@/components/app/ArtifactWorkspace";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileText, ScrollText, Play, Upload } from "lucide-react";
import type { VideoData } from "@/pages/MainApp";
import type { WorkspaceJobStatus } from "@/services/api";

interface CenterPanelProps {
  processingState: "idle" | "processing" | "completed" | "error";
  videoData: VideoData | null;
  workspaceJob?: WorkspaceJobStatus | null;
  currentTimestamp: number;
  onTimestampJump: (timestamp: number) => void;
  onRetryJob?: (jobId: string) => void;
}

const CenterPanel = ({ 
  processingState, 
  videoData, 
  workspaceJob,
  currentTimestamp,
  onTimestampJump,
  onRetryJob,
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
                  Upload a local video file and describe the artifact you want VidSnap to create.
                </p>
              </div>
              
              <div className="pt-4">
                <div className="inline-flex items-center gap-2 rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                  <Upload className="w-3.5 h-3.5" />
                  MP4, MOV, MKV, AVI, WEBM, and M4V are supported.
                </div>
              </div>
            </div>
          </div>
        )}

        {processingState === "processing" && (
          <ProcessingStatus job={workspaceJob} onRetry={onRetryJob} />
        )}

        {processingState === "error" && workspaceJob && (
          <ProcessingStatus job={workspaceJob} onRetry={onRetryJob} />
        )}

        {processingState === "completed" && videoData && (
          <div className="space-y-6">
            {videoData.artifact ? (
              <ArtifactWorkspace videoData={videoData} />
            ) : (
              <>
                <TimelineNavigator 
                  keyframes={videoData.keyframes}
                  duration={videoData.duration}
                  currentTimestamp={currentTimestamp}
                  onTimestampClick={onTimestampJump}
                />
                
                <Tabs defaultValue="summary" className="w-full">
                  <TabsList className="grid w-full grid-cols-2 mb-6 bg-muted/50 p-1 rounded-xl">
                    <TabsTrigger value="summary" className="gap-2 rounded-lg data-[state=active]:bg-card data-[state=active]:shadow-sm">
                      <FileText className="w-4 h-4" />
                      Summary
                    </TabsTrigger>
                    <TabsTrigger value="transcript" className="gap-2 rounded-lg data-[state=active]:bg-card data-[state=active]:shadow-sm">
                      <ScrollText className="w-4 h-4" />
                      Transcript
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="summary">
                    <SummaryView videoData={videoData} />
                  </TabsContent>

                  <TabsContent value="transcript">
                    <TranscriptViewer transcript={videoData.transcript} />
                  </TabsContent>
                </Tabs>
              </>
            )}
          </div>
        )}
        
        {processingState === "error" && !workspaceJob && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center space-y-4 max-w-md">
              <div className="w-16 h-16 mx-auto rounded-2xl bg-destructive/10 flex items-center justify-center">
                <span className="text-3xl">❌</span>
              </div>
              <h2 className="text-lg font-semibold text-destructive">Processing Failed</h2>
              <p className="text-sm text-muted-foreground">
                Something went wrong while processing your video. Please check the file and try again.
              </p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
};

export default CenterPanel;
