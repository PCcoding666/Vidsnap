import { Progress } from "@/components/ui/progress";
import { CheckCircle2, Clock, Loader2 } from "lucide-react";

const steps = [
  { id: 1, label: "视频下载完成", status: "completed", time: "2s" },
  { id: 2, label: "关键帧提取完成", status: "completed", time: "8s" },
  { id: 3, label: "音频转录中", status: "processing", time: "预计还需 30s" },
  { id: 4, label: "AI 总结生成", status: "pending", time: "" },
];

const ProcessingStatus = () => {
  const progress = 45;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-card rounded-2xl p-8 shadow-lg border border-border">
        <div className="space-y-6">
          <div>
            <div className="flex items-center gap-3 mb-4">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <h2 className="text-xl font-semibold">
                正在处理: "如何学习编程..."
              </h2>
            </div>
            
            <Progress value={progress} className="h-3" />
            <p className="text-sm text-muted-foreground mt-2">
              当前进度: {progress}%
            </p>
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-muted-foreground">
              处理步骤
            </h3>
            
            {steps.map((step) => (
              <div
                key={step.id}
                className="flex items-start gap-4 p-4 rounded-lg bg-muted/30"
              >
                <div className="mt-1">
                  {step.status === "completed" && (
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                  )}
                  {step.status === "processing" && (
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                  )}
                  {step.status === "pending" && (
                    <Clock className="w-5 h-5 text-muted-foreground" />
                  )}
                </div>
                
                <div className="flex-1">
                  <p className="font-medium">{step.label}</p>
                  {step.time && (
                    <p className="text-sm text-muted-foreground mt-1">
                      {step.time}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProcessingStatus;
