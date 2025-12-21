import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Copy, Search } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface TranscriptViewerProps {
  transcript: string;
}

const TranscriptViewer = ({ transcript }: TranscriptViewerProps) => {
  const [searchQuery, setSearchQuery] = useState("");
  const { toast } = useToast();

  const handleCopyTranscript = () => {
    navigator.clipboard.writeText(transcript);
    toast({
      title: "已复制",
      description: "转录文本已复制到剪贴板",
    });
  };

  return (
    <Card className="p-6">
      <div className="flex items-center gap-4 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="搜索转录内容..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Button variant="outline" className="gap-2" onClick={handleCopyTranscript}>
          <Copy className="w-4 h-4" />
          复制全文
        </Button>
      </div>

      <ScrollArea className="h-[500px]">
        <div className="prose prose-sm max-w-none">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{transcript}</p>
        </div>
      </ScrollArea>
    </Card>
  );
};

export default TranscriptViewer;
