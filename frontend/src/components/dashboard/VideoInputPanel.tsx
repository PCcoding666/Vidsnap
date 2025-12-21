import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Youtube, Upload, Sparkles, Loader2, ChevronDown } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

interface VideoInputPanelProps {
  onStartProcessing: (input: string | File, type: "youtube" | "upload") => void;
  disabled?: boolean;
}

const VideoInputPanel = ({ onStartProcessing, disabled = false }: VideoInputPanelProps) => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [inputType, setInputType] = useState<"youtube" | "upload">("youtube");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("auto");
  const [enableDiarization, setEnableDiarization] = useState(true);
  const [autoChapters, setAutoChapters] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleSubmit = () => {
    if (inputType === "youtube") {
      if (!youtubeUrl) {
        toast({
          variant: "destructive",
          title: "Missing URL",
          description: "Please enter a YouTube video URL",
        });
        return;
      }
      onStartProcessing(youtubeUrl, "youtube");
    } else if (inputType === "upload") {
      if (!file) {
        toast({
          variant: "destructive",
          title: "No file selected",
          description: "Please select a video file to upload",
        });
        return;
      }
      onStartProcessing(file, "upload");
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const isButtonDisabled = disabled || (inputType === "youtube" ? !youtubeUrl : !file);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h2 className="text-sm font-medium text-foreground mb-1">Video Input</h2>
        <p className="text-xs text-muted-foreground">Paste a URL or upload a file</p>
      </div>

      {/* Segmented Control Toggle */}
      <div className="flex p-1 bg-muted/50 rounded-xl">
        <button
          onClick={() => setInputType("youtube")}
          disabled={disabled}
          className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
            inputType === "youtube"
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <Youtube className="w-4 h-4" />
          YouTube
        </button>
        <button
          onClick={() => setInputType("upload")}
          disabled={disabled}
          className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
            inputType === "upload"
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <Upload className="w-4 h-4" />
          Upload
        </button>
      </div>

      {/* Input Content */}
      {inputType === "youtube" ? (
        <div className="space-y-2">
          <Input
            placeholder="https://www.youtube.com/watch?v=..."
            value={youtubeUrl}
            onChange={(e) => setYoutubeUrl(e.target.value)}
            className="h-12 bg-background text-sm"
            disabled={disabled}
          />
          <p className="text-[11px] text-muted-foreground">
            Supports YouTube, Bilibili, and other major platforms
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className={`border-2 border-dashed rounded-xl p-5 text-center transition-all ${
            disabled ? 'bg-muted/30 cursor-not-allowed' : 'hover:border-primary/50 cursor-pointer'
          } ${file ? 'border-primary/50 bg-primary/5' : 'border-border'}`}>
            <input
              id="file-upload"
              type="file"
              accept="video/mp4,video/avi,video/mov,video/mkv"
              onChange={handleFileChange}
              className="hidden"
              disabled={disabled}
            />
            <label htmlFor="file-upload" className={disabled ? 'cursor-not-allowed' : 'cursor-pointer'}>
              <Upload className={`w-8 h-8 mx-auto mb-2 ${file ? 'text-primary' : 'text-muted-foreground'}`} />
              {file ? (
                <div>
                  <p className="font-medium text-sm">{file.name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB
                  </p>
                </div>
              ) : (
                <div>
                  <p className="font-medium text-sm">Click to upload</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    MP4, AVI, MOV, MKV
                  </p>
                </div>
              )}
            </label>
          </div>
        </div>
      )}

      {/* Processing Parameters - Collapsible */}
      <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
        <CollapsibleTrigger asChild>
          <button className="flex items-center justify-between w-full text-xs text-muted-foreground hover:text-foreground transition-colors py-2">
            <span>Advanced Options</span>
            <ChevronDown className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-4 pt-2">
          <div className="space-y-2">
            <Label htmlFor="language" className="text-xs text-muted-foreground">Language</Label>
            <Select value={language} onValueChange={setLanguage} disabled={disabled}>
              <SelectTrigger id="language" className="h-9 text-sm">
                <SelectValue placeholder="Select language" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto detect</SelectItem>
                <SelectItem value="zh">Chinese</SelectItem>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="ja">Japanese</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-3">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="diarization"
                checked={enableDiarization}
                onCheckedChange={(checked) => setEnableDiarization(checked as boolean)}
                disabled={disabled}
              />
              <Label htmlFor="diarization" className="text-xs font-normal cursor-pointer text-muted-foreground">
                Speaker diarization
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="chapters"
                checked={autoChapters}
                onCheckedChange={(checked) => setAutoChapters(checked as boolean)}
                disabled={disabled}
              />
              <Label htmlFor="chapters" className="text-xs font-normal cursor-pointer text-muted-foreground">
                Auto chapters
              </Label>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Submit Button */}
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
            Start Analysis
          </>
        )}
      </Button>
    </div>
  );
};

export default VideoInputPanel;