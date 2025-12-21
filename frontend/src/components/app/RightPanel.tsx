import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Send, Sparkles, User, Bot, X, MessageSquare, Zap, FileSearch, Video } from "lucide-react";
import type { VideoData } from "@/pages/MainApp";
import { apiService } from "@/services/api";
import { useToast } from "@/hooks/use-toast";
import StreamingMessage from "@/components/chat/StreamingMessage";
import MarkdownRenderer from "@/components/chat/MarkdownRenderer";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp?: number;
  relatedKeyframes?: number[];
  imageUrls?: string[];
  imageFrameIds?: number[];
}

interface RightPanelProps {
  videoData: VideoData | null;
  onTimestampJump: (timestamp: number) => void;
  onHighlightKeyframes: (frameIds: number[]) => void;
  selectedKeyframe?: { id: number; url: string } | null;
  onKeyframeUsed?: () => void;
}

const RightPanel = ({ 
  videoData, 
  onTimestampJump, 
  onHighlightKeyframes, 
  selectedKeyframe,
  onKeyframeUsed
}: RightPanelProps) => {
  const { toast } = useToast();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [selectedKeyframes, setSelectedKeyframes] = useState<Array<{ id: number; url: string }>>([]);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const MAX_KEYFRAMES = 5;
  const sessionReady = sessionId !== null;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);
  
  useEffect(() => {
    if (selectedKeyframe) {
      if (selectedKeyframes.length >= MAX_KEYFRAMES) {
        toast({
          variant: "destructive",
          title: "已达上限",
          description: `最多只能选择 ${MAX_KEYFRAMES} 张关键帧`,
        });
        return;
      }
      
      if (selectedKeyframes.some(kf => kf.id === selectedKeyframe.id)) {
        toast({
          title: "已选择",
          description: `关键帧 #${selectedKeyframe.id} 已在选择列表中`,
        });
        return;
      }
      
      setSelectedKeyframes(prev => [...prev, selectedKeyframe]);
      if (selectedKeyframes.length === 0) {
        setInput("请分析这些场景的内容");
      }
      toast({
        title: "关键帧已添加",
        description: `已选中 ${selectedKeyframes.length + 1}/${MAX_KEYFRAMES} 张关键帧`,
      });
    }
  }, [selectedKeyframe]);
  
  useEffect(() => {
    if (videoData && !sessionId) {
      initializeChatSession();
    }
  }, [videoData]);

  const initializeChatSession = async () => {
    if (!videoData || isInitializing) return;
    
    setIsInitializing(true);
    try {
      const response = await apiService.startChatSession({
        video_id: videoData.id
      });

      if (response.status === "success") {
        setSessionId(response.session_id);
        console.log("✅ 聊天会话已初始化:", response.session_id);
      }
    } catch (error: any) {
      console.error("聊天会话初始化失败:", error);
      toast({
        variant: "destructive",
        title: "会话初始化失败",
        description: error.message || "无法启动聊天功能",
      });
    } finally {
      setIsInitializing(false);
    }
  };

  const suggestedQuestions = [
    "What's the main topic?",
    "Key takeaways?",
    "Summarize briefly",
  ];

  const handleSend = async () => {
    if (!input.trim() || !sessionReady || isSending) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      imageUrls: selectedKeyframes.length > 0 ? selectedKeyframes.map(kf => kf.url) : undefined,
      imageFrameIds: selectedKeyframes.length > 0 ? selectedKeyframes.map(kf => kf.id) : undefined,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsSending(true);

    const aiMessageId = (Date.now() + 1).toString();
    const placeholderMessage: Message = {
      id: aiMessageId,
      role: "assistant",
      content: "",
    };
    setMessages((prev) => [...prev, placeholderMessage]);
    setStreamingMessageId(aiMessageId);

    try {
      const response = await apiService.sendChatMessage({
        session_id: sessionId!,
        question: userMessage.content,
        keyframe_ids: selectedKeyframes.length > 0 ? selectedKeyframes.map(kf => kf.id) : undefined,
        top_k: 5,
        auto_keyframes: false,
      });

      if (response.status === "success") {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === aiMessageId
              ? {
                  ...msg,
                  content: response.answer,
                  timestamp:
                    response.references?.time_ranges?.[0]?.start_time,
                  relatedKeyframes: response.references?.keyframe_ids,
                }
              : msg
          )
        );

        if (response.references?.keyframe_ids && response.references.keyframe_ids.length > 0) {
          onHighlightKeyframes(response.references.keyframe_ids);
        }

        setTimeout(() => {
          setStreamingMessageId(null);
        }, response.answer.length * 20 + 500);
      }
    } catch (error: any) {
      console.error("发送消息失败:", error);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? {
                ...msg,
                content: `❌ Sorry, an error occurred: ${error.message || 'Unable to get response'}`,
              }
            : msg
        )
      );
      setStreamingMessageId(null);
    } finally {
      setIsSending(false);
      setSelectedKeyframes([]);
      onKeyframeUsed?.();
    }
  };

  const handleRemoveKeyframe = (frameId: number) => {
    setSelectedKeyframes(prev => prev.filter(kf => kf.id !== frameId));
  };

  const handleQuestionClick = (question: string) => {
    setInput(question);
  };

  const handleTimestampClick = (timestamp: number) => {
    onTimestampJump(timestamp);
  };

  return (
    <aside className="w-[320px] flex-shrink-0 flex flex-col">
      <div className="flex-1 flex flex-col bg-card rounded-2xl border border-border/60 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-border/60">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-primary to-accent rounded-xl">
              <Sparkles className="w-4 h-4 text-primary-foreground" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-medium text-foreground">AI Assistant</h3>
              <p className="text-xs text-muted-foreground">Chat with your video</p>
            </div>
            {sessionReady ? (
              <div className="flex items-center gap-1.5 text-xs text-green-600 bg-green-500/10 px-2 py-1 rounded-full">
                <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                Ready
              </div>
            ) : isInitializing ? (
              <div className="flex items-center gap-1.5 text-xs text-blue-600 bg-blue-500/10 px-2 py-1 rounded-full">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                Loading...
              </div>
            ) : null}
          </div>
        </div>

        {/* Messages Area */}
        <ScrollArea className="flex-1 px-4 py-4" ref={scrollAreaRef}>
          <div className="space-y-4">
            {/* Welcome Message - 未处理视频时显示 */}
            {!sessionReady && !isInitializing && (
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center">
                  <Bot className="w-4 h-4 text-primary-foreground" />
                </div>
                <div className="flex-1 bg-muted/50 rounded-2xl rounded-tl-md px-4 py-3">
                  <p className="text-sm text-foreground font-medium mb-2">
                    👋 Hi! I'm your video assistant.
                  </p>
                  <p className="text-xs text-muted-foreground mb-3">
                    Upload a video and I can help you:
                  </p>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <FileSearch className="w-3.5 h-3.5 text-primary" />
                      <span>Generate summaries</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <MessageSquare className="w-3.5 h-3.5 text-primary" />
                      <span>Answer questions</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Zap className="w-3.5 h-3.5 text-primary" />
                      <span>Extract key insights</span>
                    </div>
                  </div>
                  <div className="mt-4 pt-3 border-t border-border/50 flex items-center gap-2 text-xs text-muted-foreground">
                    <Video className="w-3.5 h-3.5" />
                    <span>Paste a YouTube URL to get started →</span>
                  </div>
                </div>
              </div>
            )}
            
            {/* 会话就绪但无消息时的提示 */}
            {messages.length === 0 && sessionReady && (
              <div className="text-center py-6">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-br from-primary/10 to-accent/10 mb-3">
                  <Bot className="w-6 h-6 text-primary" />
                </div>
                <p className="text-xs text-muted-foreground">Ready to answer your questions</p>
              </div>
            )}
            
            {messages.map((message) => {
              const isUser = message.role === "user";
              const isStreaming = streamingMessageId === message.id;
              
              return (
                <div
                  key={message.id}
                  className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
                >
                  {!isUser && (
                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center">
                      <Bot className="w-4 h-4 text-primary-foreground" />
                    </div>
                  )}
                  
                  <div className={`flex flex-col max-w-[85%] ${isUser ? "items-end" : "items-start"}`}>
                    {isUser && message.imageUrls && message.imageUrls.length > 0 && (
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        {message.imageUrls.map((url, idx) => (
                          <div key={idx} className="rounded-lg overflow-hidden border border-border shadow-sm">
                            <img 
                              src={url} 
                              alt={`Frame ${idx + 1}`}
                              className="max-w-[100px] max-h-[75px] object-cover"
                            />
                            <div className="bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground text-center">
                              #{message.imageFrameIds?.[idx]}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    
                    <div
                      className={`rounded-2xl px-3.5 py-2.5 ${
                        isUser
                          ? "bg-gradient-to-br from-primary to-accent text-primary-foreground rounded-tr-md"
                          : "bg-muted/50 rounded-tl-md"
                      }`}
                    >
                      {isUser ? (
                        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      ) : isStreaming ? (
                        <StreamingMessage content={message.content} isStreaming={true} speed={15} />
                      ) : (
                        <MarkdownRenderer content={message.content} />
                      )}
                    </div>
                    
                    {!isUser && message.timestamp !== undefined && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="mt-1.5 h-7 text-xs hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                        onClick={() => handleTimestampClick(message.timestamp!)}
                      >
                        <span className="mr-1">🎬</span>
                        Jump to {Math.floor(message.timestamp / 60)}:{String(Math.floor(message.timestamp % 60)).padStart(2, '0')}
                      </Button>
                    )}
                  </div>
                  
                  {isUser && (
                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-muted flex items-center justify-center">
                      <User className="w-4 h-4 text-muted-foreground" />
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input Area */}
        {sessionReady && (
          <div className="p-4 border-t border-border/60 space-y-3">
            {/* 推荐问题 */}
            <div className="flex flex-wrap gap-1.5">
              {suggestedQuestions.map((q, i) => (
                <Button
                  key={i}
                  variant="outline"
                  size="sm"
                  className="text-xs h-7 px-2.5 hover:bg-primary/10 hover:text-primary hover:border-primary/50 transition-all"
                  onClick={() => handleQuestionClick(q)}
                  disabled={isSending}
                >
                  {q}
                </Button>
              ))}
            </div>

            {/* 输入框 */}
            <div className="flex flex-col gap-2">
              {selectedKeyframes.length > 0 && (
                <div className="flex flex-wrap gap-1.5 p-2 bg-muted/30 rounded-lg">
                  {selectedKeyframes.map((kf) => (
                    <div key={kf.id} className="relative group">
                      <img 
                        src={kf.url} 
                        alt={`Frame #${kf.id}`}
                        className="h-12 rounded border-2 border-primary"
                      />
                      <button
                        onClick={() => handleRemoveKeyframe(kf.id)}
                        className="absolute -top-1.5 -right-1.5 bg-destructive text-destructive-foreground rounded-full w-4 h-4 flex items-center justify-center text-xs hover:bg-destructive/90 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <X className="w-2.5 h-2.5" />
                      </button>
                      <div className="absolute bottom-0 left-0 right-0 bg-black/70 text-white text-[10px] px-1 text-center">
                        #{kf.id}
                      </div>
                    </div>
                  ))}
                  <div className="text-[10px] text-muted-foreground self-center px-1.5">
                    {selectedKeyframes.length}/{MAX_KEYFRAMES}
                  </div>
                </div>
              )}
              
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && !isSending && handleSend()}
                    placeholder={selectedKeyframes.length > 0 ? `Ask about ${selectedKeyframes.length} frame(s)...` : "Ask anything..."}
                    className="pr-10 bg-background h-10 text-sm"
                    disabled={isSending}
                  />
                  {isSending && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                      <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}
                </div>
                <Button 
                  onClick={handleSend} 
                  size="icon"
                  disabled={isSending || !input.trim()}
                  className="h-10 w-10 bg-gradient-to-br from-primary to-accent hover:opacity-90 hover:scale-105 active:scale-95 transition-all"
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};

export default RightPanel;