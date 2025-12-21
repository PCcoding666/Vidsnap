import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { Components } from 'react-markdown';

interface MarkdownRendererProps {
  content: string;
}

const MarkdownRenderer = ({ content }: MarkdownRendererProps) => {
  const components: Components = {
    code(props) {
      const { children, className } = props;
      const match = /language-(\w+)/.exec(className || '');
      const isInline = !match;
      
      return !isInline ? (
        <SyntaxHighlighter
          style={oneDark as any}
          language={match[1]}
          PreTag="div"
          className="rounded-lg !mt-2 !mb-2"
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">
          {children}
        </code>
      );
    },
    a(props) {
      const { children, href } = props;
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          {children}
        </a>
      );
    },
    table(props) {
      const { children } = props;
      return (
        <div className="overflow-x-auto my-4">
          <table className="min-w-full divide-y divide-border">
            {children}
          </table>
        </div>
      );
    },
    th(props) {
      const { children } = props;
      return (
        <th className="px-4 py-2 bg-muted font-semibold text-left">
          {children}
        </th>
      );
    },
    td(props) {
      const { children } = props;
      return (
        <td className="px-4 py-2 border-t border-border">
          {children}
        </td>
      );
    },
    blockquote(props) {
      const { children } = props;
      return (
        <blockquote className="border-l-4 border-primary pl-4 py-2 my-4 italic bg-muted/30">
          {children}
        </blockquote>
      );
    },
    h1(props) {
      const { children } = props;
      return <h1 className="text-2xl font-bold mt-6 mb-4">{children}</h1>;
    },
    h2(props) {
      const { children } = props;
      return <h2 className="text-xl font-bold mt-5 mb-3">{children}</h2>;
    },
    h3(props) {
      const { children } = props;
      return <h3 className="text-lg font-bold mt-4 mb-2">{children}</h3>;
    },
    ul(props) {
      const { children } = props;
      return <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>;
    },
    ol(props) {
      const { children } = props;
      return <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>;
    },
    li(props) {
      const { children } = props;
      return <li className="ml-4">{children}</li>;
    },
  };

  return (
    <div className="prose prose-sm dark:prose-invert max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;
