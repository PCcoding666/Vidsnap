import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import SummaryView from "./SummaryView";
import KeyframesGallery from "./KeyframesGallery";
import VideoChatBot from "./VideoChatBot";
import TranscriptViewer from "./TranscriptViewer";
import { FileText, Image, MessageSquare, ScrollText } from "lucide-react";

interface ResultTabsProps {
  videoData: any;
}

const ResultTabs = ({ videoData }: ResultTabsProps) => {
  return (
    <Tabs defaultValue="summary" className="w-full">
      <TabsList className="grid w-full grid-cols-4 mb-8">
        <TabsTrigger value="summary" className="gap-2">
          <FileText className="w-4 h-4" />
          内容总结
        </TabsTrigger>
        <TabsTrigger value="keyframes" className="gap-2">
          <Image className="w-4 h-4" />
          关键帧
        </TabsTrigger>
        <TabsTrigger value="chat" className="gap-2">
          <MessageSquare className="w-4 h-4" />
          对话
        </TabsTrigger>
        <TabsTrigger value="transcript" className="gap-2">
          <ScrollText className="w-4 h-4" />
          转录文本
        </TabsTrigger>
      </TabsList>

      <TabsContent value="summary">
        <SummaryView videoData={videoData} />
      </TabsContent>

      <TabsContent value="keyframes">
        <KeyframesGallery keyframes={[]} />
      </TabsContent>

      <TabsContent value="chat">
        <VideoChatBot />
      </TabsContent>

      <TabsContent value="transcript">
        <TranscriptViewer transcript="" />
      </TabsContent>
    </Tabs>
  );
};

export default ResultTabs;
