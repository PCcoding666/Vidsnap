import React, { useState, useEffect } from 'react';
import { Input, Button, Card, message, Alert } from 'antd';
import { YoutubeOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const Home = () => {
  const [videoUrl, setVideoUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState('');
  const [error, setError] = useState('');
  const [pollingIntervalId, setPollingIntervalId] = useState(null);
  const [currentSummaryId, setCurrentSummaryId] = useState(null);

  const pollSummary = async (summaryId) => {
    try {
      const response = await fetch(`http://localhost:8000/api/v1/summaries/${summaryId}`);
      if (!response.ok) {
        stopPolling();
        return;
      }

      const data = await response.json();
      console.log('轮询状态:', data.status, 'ID:', summaryId);

      if (data.status === 'completed') {
        stopPolling();
        setSummary(data.summary_text || '摘要生成完毕，但内容为空');
        setLoading(false);
      } else if (data.status === 'failed') {
        stopPolling();
        setError(`摘要生成失败: ${data.error_message || '未知错误'}`);
        setLoading(false);
      }
    } catch (err) {
      console.error('轮询过程中出错:', err);
      stopPolling();
      setError(`轮询过程中出错: ${err.message}`);
      setLoading(false);
    }
  };

  const startPolling = (summaryId) => {
    stopPolling();
    setCurrentSummaryId(summaryId);

    const intervalId = setInterval(() => {
      pollSummary(summaryId);
    }, 5000);
    setPollingIntervalId(intervalId);

    setTimeout(() => {
      if (pollingIntervalId) {
        console.log('轮询超时，停止轮询');
        stopPolling();
        if (loading) {
          setError('处理超时，请稍后再试');
          setLoading(false);
        }
      }
    }, 300000);
  };

  const stopPolling = () => {
    if (pollingIntervalId) {
      clearInterval(pollingIntervalId);
      setPollingIntervalId(null);
      setCurrentSummaryId(null);
    }
  };

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, []);

  const handleSubmit = async () => {
    if (!videoUrl.trim()) {
      setError('请输入YouTube视频URL');
      return;
    }

    setLoading(true);
    setError(null);
    setSummary(null);
    stopPolling();

    try {
      const response = await fetch('http://localhost:8000/api/v1/summaries', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ video_url: videoUrl }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData?.detail?.message || `服务器错误: ${response.status}`);
      }

      const initialData = await response.json();
      console.log('初始API响应数据:', initialData);

      if (initialData.id && (initialData.status === 'pending' || initialData.status === 'processing')) {
        message.info('收到摘要请求，正在后台处理...');
        startPolling(initialData.id);
      } else if (initialData.id && initialData.status === 'completed') {
        setSummary(initialData.summary_text || '摘要已完成但内容为空');
        setLoading(false);
      } else if (initialData.id && initialData.status === 'failed') {
        setError(`摘要生成失败: ${initialData.error_message || '未知初始错误'}`);
        setLoading(false);
      } else {
        console.error('无效的初始响应格式:', initialData);
        throw new Error('无法开始处理摘要，响应格式不正确');
      }

    } catch (err) {
      setError(`请求失败: ${err.message}`);
      setLoading(false);
      stopPolling();
    } finally {
    }
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '20px' }}>
      <Card title="输入YouTube视频链接" bordered={false}>
        <Input
          size="large"
          placeholder="请粘贴YouTube视频链接"
          prefix={<YoutubeOutlined />}
          value={videoUrl}
          onChange={(e) => setVideoUrl(e.target.value)}
          style={{ marginBottom: '20px' }}
        />
        <Button
          type="primary"
          size="large"
          loading={loading}
          onClick={handleSubmit}
          block
        >
          生成视频摘要
        </Button>
      </Card>
      
      {error && (
        <Card title="错误信息" style={{ marginTop: '20px', borderColor: '#ff4d4f' }}>
          <Alert
            message="生成摘要时出错"
            description={error}
            type="error"
            showIcon
          />
        </Card>
      )}
      
      {summary && (
        <Card title="当前视频摘要结果" style={{ marginTop: '20px' }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {summary}
          </ReactMarkdown>
        </Card>
      )}
    </div>
  );
};

export default Home; 