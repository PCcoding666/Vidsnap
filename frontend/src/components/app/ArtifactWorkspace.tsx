import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import MarkdownRenderer from "@/components/chat/MarkdownRenderer";
import { CheckCircle2, CircleDashed, Clipboard, FileText, GitBranch, ListChecks } from "lucide-react";
import type { VideoData } from "@/pages/MainApp";

interface ArtifactWorkspaceProps {
  videoData: VideoData;
}

const artifactLabels: Record<string, string> = {
  transcript: "Transcript",
  summary: "Summary",
  notes: "Notes",
  content_locations: "Locations",
  qa_answer: "Answer",
};

const formatTime = (seconds: number) => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
};

const ArtifactWorkspace = ({ videoData }: ArtifactWorkspaceProps) => {
  const artifact = videoData.artifact;
  const plan = videoData.plan;
  const trace = videoData.skillTrace || [];

  if (!artifact || !plan) {
    return null;
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(artifact.content);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{artifactLabels[artifact.artifact_type] || artifact.artifact_type}</Badge>
            <Badge variant={plan.cost_tier === "high" ? "destructive" : "outline"}>
              {plan.cost_tier} cost
            </Badge>
            {plan.requires_user_confirmation && (
              <Badge variant="outline">visual request</Badge>
            )}
          </div>
          <h2 className="text-xl font-semibold text-foreground">{artifact.title}</h2>
          {videoData.userQuery && (
            <p className="text-sm text-muted-foreground">{videoData.userQuery}</p>
          )}
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={handleCopy}>
          <Clipboard className="h-4 w-4" />
          Copy
        </Button>
      </div>

      <Tabs defaultValue="artifact" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="artifact" className="gap-2">
            <FileText className="h-4 w-4" />
            Artifact
          </TabsTrigger>
          <TabsTrigger value="plan" className="gap-2">
            <GitBranch className="h-4 w-4" />
            Plan
          </TabsTrigger>
          <TabsTrigger value="trace" className="gap-2">
            <ListChecks className="h-4 w-4" />
            Trace
          </TabsTrigger>
        </TabsList>

        <TabsContent value="artifact" className="mt-5">
          <Card className="p-5">
            <div className="prose prose-sm dark:prose-invert max-w-none">
              {artifact.format === "markdown" ? (
                <MarkdownRenderer content={artifact.content} />
              ) : (
                <pre className="whitespace-pre-wrap text-sm">{artifact.content}</pre>
              )}
            </div>
          </Card>

          {artifact.citations.length > 0 && (
            <Card className="mt-4 p-5">
              <h3 className="mb-3 text-sm font-medium text-foreground">Transcript Citations</h3>
              <div className="space-y-2">
                {artifact.citations.slice(0, 8).map((citation, index) => (
                  <div key={`${citation.start_time}-${index}`} className="rounded-md border border-border/70 p-3">
                    <div className="mb-1 text-xs font-medium text-primary">
                      {formatTime(citation.start_time)} - {formatTime(citation.end_time)}
                    </div>
                    <p className="text-sm text-muted-foreground">{citation.text}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="plan" className="mt-5">
          <Card className="p-5">
            <div className="mb-4">
              <h3 className="text-sm font-medium text-foreground">Skill Plan</h3>
              <p className="text-xs text-muted-foreground">{plan.plan_id}</p>
            </div>
            <div className="space-y-3">
              {plan.steps.map((step, index) => (
                <div key={step.id} className="rounded-md border border-border/70 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-medium">
                        {index + 1}
                      </span>
                      <span className="text-sm font-medium">{step.skill}</span>
                    </div>
                    {step.depends_on.length > 0 && (
                      <span className="text-xs text-muted-foreground">
                        after {step.depends_on.join(", ")}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{step.purpose}</p>
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="trace" className="mt-5">
          <Card className="p-5">
            <div className="space-y-3">
              {trace.map((entry) => (
                <div key={entry.step_id} className="flex items-start gap-3 rounded-md border border-border/70 p-3">
                  {entry.status === "success" ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 text-green-600" />
                  ) : (
                    <CircleDashed className="mt-0.5 h-4 w-4 text-muted-foreground" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{entry.skill}</span>
                      <Badge variant={entry.status === "failed" ? "destructive" : "outline"}>
                        {entry.status}
                      </Badge>
                      {entry.duration_ms !== undefined && (
                        <span className="text-xs text-muted-foreground">{entry.duration_ms}ms</span>
                      )}
                    </div>
                    {entry.output_summary && (
                      <p className="mt-1 text-sm text-muted-foreground">{entry.output_summary}</p>
                    )}
                    {entry.error && (
                      <p className="mt-1 text-sm text-destructive">{entry.error}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ArtifactWorkspace;
