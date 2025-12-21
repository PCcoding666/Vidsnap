import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Send, Sparkles } from "lucide-react";

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

const VideoChatBot = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      role: "assistant",
      content: "你好！我已经分析完这个视频。你可以问我任何关于视频内容的问题。",
    },
  ]);
  const [input, setInput] = useState("");

  const suggestedQuestions = [
    "这个视频主要讲什么？",
    "有哪些关键步骤？",
    "最重要的建议是什么？",
  ];

  const handleSend = () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: messages.length + 1,
      role: "user",
      content: input,
    };

    const aiResponse: Message = {
      id: messages.length + 2,
      role: "assistant",
      content: "这是一个示例回复。在实际应用中，这里会连接到后端 AI 服务。",
      timestamp: "02:15",
    };

    setMessages([...messages, userMessage, aiResponse]);
    setInput("");
  };

  return (
    <Card className="p-6 h-[600px] flex flex-col">
      <ScrollArea className="flex-1 pr-4 mb-4">
        <div className="space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                  message.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                {message.role === "assistant" && (
                  <div className="flex items-center gap-2 mb-2">
                    <Sparkles className="w-4 h-4 text-primary" />
                    <span className="text-xs font-semibold">AI 助手</span>
                  </div>
                )}
                <p className="text-sm leading-relaxed">{message.content}</p>
                {message.timestamp && (
                  <Button
                    variant="link"
                    size="sm"
                    className="mt-2 p-0 h-auto text-xs"
                  >
                    🎬 跳转到 {message.timestamp}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <p className="text-xs text-muted-foreground w-full mb-1">💡 推荐问题：</p>
          {suggestedQuestions.map((question, index) => (
            <Button
              key={index}
              variant="outline"
              size="sm"
              onClick={() => setInput(question)}
              className="text-xs"
            >
              {question}
            </Button>
          ))}
        </div>

        <div className="flex gap-2">
          <Input
            placeholder="输入你的问题..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && handleSend()}
          />
          <Button onClick={handleSend} size="icon">
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </Card>
  );
};

export default VideoChatBot;
