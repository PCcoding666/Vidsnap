import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Upload, Sparkles, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface VideoInputPanelProps {
  onStartProcessing: (file: File, query: string) => void;
  disabled?: boolean;
}

const VideoInputPanel = ({ onStartProcessing, disabled = false }: VideoInputPanelProps) => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [query, setQuery] = useState("把这个视频整理成可复用的结构化笔记");

  const examplePrompts = [
    "制作图文并茂的笔记",
    "视频转录，按时间戳分段",
    "帮我定位提到商业模式的片段",
  ];

  const handleSubmit = () => {
    if (!file) {
      toast({
        variant: "destructive",
        title: "No file selected",
        description: "Please select a video file to upload",
      });
      return;
    }

    if (!query.trim()) {
      toast({
        variant: "destructive",
        title: "Missing goal",
        description: "Describe what you want VidSnap to produce.",
      });
      return;
    }

    onStartProcessing(file, query.trim());
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      const allowedExtensions = [".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"];
      const extension = selectedFile.name.slice(selectedFile.name.lastIndexOf(".")).toLowerCase();

      if (!allowedExtensions.includes(extension)) {
        toast({
          variant: "destructive",
          title: "Unsupported format",
          description: "Please upload MP4, MOV, MKV, AVI, WEBM, or M4V.",
        });
        e.target.value = "";
        setFile(null);
        return;
      }

      setFile(selectedFile);
    }
  };

  const isButtonDisabled = disabled || !file || !query.trim();

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-sm font-medium text-foreground mb-1">Video Goal</h2>
        <p className="text-xs text-muted-foreground">Upload a local video and describe the artifact you need.</p>
      </div>

      <div className="space-y-2">
        <div className={`border-2 border-dashed rounded-xl p-5 text-center transition-all ${
          disabled ? "bg-muted/30 cursor-not-allowed" : "hover:border-primary/50 cursor-pointer"
        } ${file ? "border-primary/50 bg-primary/5" : "border-border"}`}>
          <input
            id="file-upload"
            type="file"
            accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm,.mp4,.mov,.mkv,.avi,.webm,.m4v"
            onChange={handleFileChange}
            className="hidden"
            disabled={disabled}
          />
          <label htmlFor="file-upload" className={disabled ? "cursor-not-allowed" : "cursor-pointer"}>
            <Upload className={`w-8 h-8 mx-auto mb-2 ${file ? "text-primary" : "text-muted-foreground"}`} />
            {file ? (
              <div>
                <p className="font-medium text-sm break-all">{file.name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {(file.size / (1024 * 1024)).toFixed(2)} MB
                </p>
              </div>
            ) : (
              <div>
                <p className="font-medium text-sm">Click to upload</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  MP4, MOV, MKV, AVI, WEBM, M4V
                </p>
              </div>
            )}
          </label>
        </div>
      </div>

      <div className="space-y-2">
        <Textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          disabled={disabled}
          className="min-h-[112px] resize-none text-sm"
          placeholder="例如：把这个 40 分钟课程整理成复习笔记，并保留重要时间戳"
        />
        <div className="flex flex-wrap gap-1.5">
          {examplePrompts.map((prompt) => (
            <Button
              key={prompt}
              type="button"
              variant="outline"
              size="sm"
              className="h-7 px-2 text-[11px]"
              disabled={disabled}
              onClick={() => setQuery(prompt)}
            >
              {prompt}
            </Button>
          ))}
        </div>
      </div>

      <Button
        className="w-full h-11 text-sm font-medium gap-2 bg-gradient-to-r from-primary to-accent hover:opacity-90 hover:scale-[1.02] active:scale-[0.98] transition-all shadow-lg shadow-primary/20"
        onClick={handleSubmit}
        disabled={isButtonDisabled}
      >
        {disabled ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            {t('common.processing')}
          </>
        ) : (
          <>
            <Sparkles className="w-4 h-4" />
            Create Artifact
          </>
        )}
      </Button>
    </div>
  );
};

export default VideoInputPanel;
