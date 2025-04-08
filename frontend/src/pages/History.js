import React, { useState, useEffect } from 'react';
import { List, Card, Button, Alert, Typography } from 'antd';
import { HistoryOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown'; // Keep markdown for potential future use (e.g., viewing full summary here)
import remarkGfm from 'remark-gfm';

const { Paragraph } = Typography;

const History = () => {
  const [historyList, setHistoryList] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [selectedSummary, setSelectedSummary] = useState(''); // State to show selected summary details

  // Function to fetch history
  const fetchHistory = async () => {
    setHistoryLoading(true);
    setHistoryError('');
    setSelectedSummary(''); // Clear selected summary when fetching
    try {
      const response = await fetch('http://localhost:8000/api/v1/summaries/history/');
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData?.detail?.message || `获取历史记录失败: ${response.status}`);
      }
      const data = await response.json();
      setHistoryList(data);
    } catch (err) {
      console.error('获取历史记录时出错:', err);
      setHistoryError(`无法加载历史记录: ${err.message}`);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Fetch history on component mount
  useEffect(() => {
    fetchHistory();
  }, []);

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '20px' }}>
      <Card 
        title={<><HistoryOutlined style={{ marginRight: 8 }} /> 历史记录</>}
        bordered={false}
      >
        {historyError && (
          <Alert message="历史记录错误" description={historyError} type="error" showIcon style={{ marginBottom: 16 }} />
        )}
        <List
          loading={historyLoading}
          itemLayout="vertical"
          dataSource={historyList}
          renderItem={(item) => (
            <List.Item key={item.id}>
              <Card 
                type="inner" 
                title={item.video_title || '无标题'} 
                extra={<a href={item.video_url} target="_blank" rel="noopener noreferrer">观看视频</a>}
              >
                <Paragraph><strong>状态:</strong> {item.status}</Paragraph>
                <Paragraph><strong>创建时间:</strong> {new Date(item.created_at).toLocaleString()}</Paragraph>
                {item.status === 'completed' && (
                  <Button size="small" onClick={() => setSelectedSummary(item.summary_text || '历史摘要内容为空')}>查看摘要</Button>
                )}
                {item.status === 'failed' && item.error_message && (
                   <Paragraph type="danger"><strong>错误:</strong> {item.error_message}</Paragraph>
                )}
              </Card>
            </List.Item>
          )}
          locale={{ emptyText: '暂无历史记录' }}
        />
      </Card>

      {/* Display selected summary details */}
      {selectedSummary && (
          <Card title="摘要详情" style={{ marginTop: '20px' }} bordered={false}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {selectedSummary}
              </ReactMarkdown>
          </Card>
      )}
    </div>
  );
};

export default History; 