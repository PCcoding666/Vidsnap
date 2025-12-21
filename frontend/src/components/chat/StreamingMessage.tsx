import { useState, useEffect } from 'react';
import MarkdownRenderer from './MarkdownRenderer';

interface StreamingMessageProps {
  content: string;
  isStreaming?: boolean;
  speed?: number; // 每个字符的延迟时间（毫秒）
}

const StreamingMessage = ({ content, isStreaming = false, speed = 20 }: StreamingMessageProps) => {
  const [displayedContent, setDisplayedContent] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (!isStreaming) {
      setDisplayedContent(content);
      return;
    }

    if (currentIndex < content.length) {
      const timeout = setTimeout(() => {
        setDisplayedContent(content.slice(0, currentIndex + 1));
        setCurrentIndex(currentIndex + 1);
      }, speed);

      return () => clearTimeout(timeout);
    }
  }, [content, currentIndex, isStreaming, speed]);

  useEffect(() => {
    // 当内容变化时重置
    setCurrentIndex(0);
    setDisplayedContent('');
  }, [content]);

  return (
    <>
      <MarkdownRenderer content={displayedContent} />
      {isStreaming && currentIndex < content.length && (
        <span className="inline-block w-1 h-4 ml-1 bg-primary animate-pulse" />
      )}
    </>
  );
};

export default StreamingMessage;
