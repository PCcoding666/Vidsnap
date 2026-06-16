import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertCircle, CheckCircle2, Clock, Loader2, RotateCcw } from "lucide-react";
import type { WorkspaceJobStatus } from "@/services/api";

interface ProcessingStatusProps {
  job?: WorkspaceJobStatus | null;
  onRetry?: (jobId: string) => void;
}

const stageLabels: Record<string, string> = {
  uploaded: "Upload saved",
  planning: "Planning",
  queued: "Queued",
  ingesting: "Preparing video",
  extracting_audio: "Extracting compressed audio",
  uploading_audio: "Uploading audio",
  transcribing: "Transcribing",
  indexing: "Building transcript index",
  generating_artifact: "Generating artifact",
  completed: "Completed",
  failed: "Failed",
};

const orderedStages = [
  "queued",
  "ingesting",
  "extracting_audio",
  "uploading_audio",
  "transcribing",
  "indexing",
  "generating_artifact",
  "completed",
];

const statusForStage = (stage: string, currentStage: string, failed: boolean) => {
  if (failed && stage === currentStage) return "failed";
  const currentIndex = orderedStages.indexOf(currentStage);
  const stageIndex = orderedStages.indexOf(stage);
  if (stageIndex < currentIndex || currentStage === "completed") return "completed";
  if (stage === currentStage) return "processing";
  return "pending";
};

const ProcessingStatus = ({ job, onRetry }: ProcessingStatusProps) => {
  const progress = job?.progress ?? 8;
  const failed = job?.status === "failed";
  const currentStage = failed ? (job?.failed_stage || job?.stage || "failed") : (job?.stage || "queued");
  const durationMinutes = job?.cost_estimate.source_duration_seconds
    ? Math.round((job.cost_estimate.source_duration_seconds / 60) * 10) / 10
    : null;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-card rounded-2xl p-8 shadow-lg border border-border">
        <div className="space-y-6">
          <div>
            <div className="flex items-center gap-3 mb-4">
              {failed ? (
                <AlertCircle className="w-6 h-6 text-destructive" />
              ) : (
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              )}
              <div className="min-w-0">
                <h2 className="text-xl font-semibold">
                  {failed ? `Failed at ${stageLabels[currentStage] || currentStage}` : stageLabels[currentStage] || currentStage}
                </h2>
                <p className="text-sm text-muted-foreground truncate">
                  {job?.original_filename || "Preparing workspace job"}
                </p>
              </div>
            </div>
            
            <Progress value={progress} className="h-3" />
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>Progress: {progress}%</span>
              {job && <Badge variant="outline">attempt {job.attempts}/{job.max_attempts}</Badge>}
              {job?.retryable && <Badge variant="destructive">retryable</Badge>}
            </div>
            {job?.message && (
              <p className="mt-2 text-sm text-muted-foreground">{job.message}</p>
            )}
            {job?.error && (
              <p className="mt-2 text-sm text-destructive">{job.error}</p>
            )}
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-muted-foreground">
              Processing stages
            </h3>
            
            {orderedStages.map((stage) => {
              const state = statusForStage(stage, currentStage, failed);
              return (
              <div
                key={stage}
                className="flex items-start gap-4 p-4 rounded-lg bg-muted/30"
              >
                <div className="mt-1">
                  {state === "completed" && (
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                  )}
                  {state === "processing" && (
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                  )}
                  {state === "failed" && (
                    <AlertCircle className="w-5 h-5 text-destructive" />
                  )}
                  {state === "pending" && (
                    <Clock className="w-5 h-5 text-muted-foreground" />
                  )}
                </div>
                
                <div className="flex-1">
                  <p className="font-medium">{stageLabels[stage]}</p>
                  {stage === "extracting_audio" && job?.cost_estimate && (
                    <p className="text-sm text-muted-foreground mt-1">
                      {job.cost_estimate.estimated_chunks} chunk(s), {job.cost_estimate.estimated_audio_mb} MB estimated {job.cost_estimate.estimated_audio_format}
                    </p>
                  )}
                  {stage === "transcribing" && job?.cost_estimate && (
                    <p className="text-sm text-muted-foreground mt-1">
                      Provider: {job.cost_estimate.provider}
                      {durationMinutes ? `, ${durationMinutes} min media` : ""}
                    </p>
                  )}
                </div>
              </div>
            )})}
          </div>

          {job?.retryable && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              <div className="flex items-center gap-2">
                <RotateCcw className="h-4 w-4" />
                <span>This job can be retried from the saved upload.</span>
              </div>
              {onRetry && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 gap-2 border-destructive/40 text-destructive hover:bg-destructive/10"
                  onClick={() => onRetry(job.job_id)}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Retry
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProcessingStatus;
