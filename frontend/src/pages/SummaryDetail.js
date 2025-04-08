import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Card, 
  Typography, 
  Button, 
  Space, 
  Tag, 
  Spin, 
  Divider, 
  Empty,
  Tabs,
  message,
  Descriptions,
  Image
} from 'antd';
import { 
  ArrowLeftOutlined, 
  StarOutlined, 
  StarFilled, 
  YoutubeOutlined,
  DeleteOutlined,
  FileTextOutlined,
  PictureOutlined,
  InfoCircleOutlined,
  WarningOutlined
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { getSummaryById, updateSummary, deleteSummary } from '../services/summaryService';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;

const SummaryDetail = ({ locale }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  // 加载摘要数据
  useEffect(() => {
    const fetchSummary = async () => {
      setLoading(true);
      try {
        const data = await getSummaryById(id);
        setSummary(data);
      } catch (error) {
        console.error('加载摘要详情失败', error);
        message.error('加载摘要详情失败: ' + error);
      } finally {
        setLoading(false);
      }
    };

    fetchSummary();
  }, [id]);

  // 切换收藏状态
  const toggleFavorite = async () => {
    try {
      const updated = await updateSummary(id, {
        is_favorite: !summary.is_favorite
      });
      setSummary(updated);
      message.success(updated.is_favorite ? '已添加到收藏' : '已从收藏中移除');
    } catch (error) {
      console.error('更新收藏状态失败', error);
      message.error('更新收藏状态失败: ' + error);
    }
  };

  // 删除摘要
  const handleDelete = async () => {
    try {
      await deleteSummary(id);
      message.success('已删除摘要');
      navigate('/history');
    } catch (error) {
      console.error('删除摘要失败', error);
      message.error('删除摘要失败: ' + error);
    }
  };

  // 处理YouTube链接点击
  const openYouTubeVideo = () => {
    if (summary && summary.video_id) {
      window.open(`https://www.youtube.com/watch?v=${summary.video_id}`, '_blank');
    }
  };

  // 状态标签颜色映射
  const statusColors = {
    pending: 'default',
    processing: 'processing',
    completed: 'success',
    failed: 'error'
  };

  // 状态文本映射
  const statusText = {
    pending: '等待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '处理失败'
  };

  // 格式化时间
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  // 格式化时长
  const formatDuration = (seconds) => {
    if (!seconds) return '未知';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}分${remainingSeconds}秒`;
  };

  // 渲染关键帧
  const renderKeyframes = () => {
    if (!summary || !summary.keyframes || summary.keyframes.length === 0) {
      return (
        <Empty 
          image={Empty.PRESENTED_IMAGE_SIMPLE} 
          description="无可用关键帧" 
        />
      );
    }

    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
        <Image.PreviewGroup>
          {summary.keyframes.map((src, index) => (
            <Image 
              key={index}
              src={src}
              alt={`关键帧 ${index + 1}`}
              style={{ width: 200, height: 200, objectFit: 'cover' }}
            />
          ))}
        </Image.PreviewGroup>
      </div>
    );
  };

  // 渲染元数据
  const renderMetadata = () => {
    if (!summary || !summary.metadata) {
      return (
        <Empty 
          image={Empty.PRESENTED_IMAGE_SIMPLE} 
          description="无可用元数据" 
        />
      );
    }

    const metadata = summary.metadata;

    return (
      <Descriptions bordered column={{ xs: 1, sm: 2 }}>
        <Descriptions.Item label="视频标题">{metadata.title || '未知'}</Descriptions.Item>
        <Descriptions.Item label="频道">{metadata.channel || '未知'}</Descriptions.Item>
        <Descriptions.Item label="上传日期">{metadata.upload_date || '未知'}</Descriptions.Item>
        <Descriptions.Item label="时长">{formatDuration(metadata.duration)}</Descriptions.Item>
        <Descriptions.Item label="观看次数">{metadata.view_count || '未知'}</Descriptions.Item>
        <Descriptions.Item label="点赞数">{metadata.like_count || '未知'}</Descriptions.Item>
        {metadata.categories && metadata.categories.length > 0 && (
          <Descriptions.Item label="类别" span={2}>
            {metadata.categories.map((category, index) => (
              <Tag key={index}>{category}</Tag>
            ))}
          </Descriptions.Item>
        )}
        {metadata.tags && metadata.tags.length > 0 && (
          <Descriptions.Item label="标签" span={2}>
            {metadata.tags.slice(0, 10).map((tag, index) => (
              <Tag key={index}>{tag}</Tag>
            ))}
            {metadata.tags.length > 10 && <Tag>...还有 {metadata.tags.length - 10} 个</Tag>}
          </Descriptions.Item>
        )}
        {metadata.description && (
          <Descriptions.Item label="描述" span={2}>
            <Paragraph ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
              {metadata.description}
            </Paragraph>
          </Descriptions.Item>
        )}
      </Descriptions>
    );
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!summary) {
    return (
      <Empty 
        description="未找到摘要" 
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  return (
    <div>
      <Card
        title={
          <Space>
            <Button 
              icon={<ArrowLeftOutlined />} 
              type="text"
              onClick={() => navigate(-1)}
            />
            <Text ellipsis style={{ maxWidth: 'calc(100vw - 300px)' }}>
              {summary.video_title || '未知视频'}
            </Text>
          </Space>
        }
        extra={
          <Space>
            <Tag color={statusColors[summary.status]}>
              {statusText[summary.status]}
            </Tag>
            <Button 
              type="text" 
              icon={<YoutubeOutlined style={{ color: 'red' }} />}
              onClick={openYouTubeVideo}
            />
            <Button 
              type="text" 
              icon={summary.is_favorite ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
              onClick={toggleFavorite}
            />
            <Button 
              type="text" 
              danger
              icon={<DeleteOutlined />}
              onClick={handleDelete}
            />
          </Space>
        }
      >
        {summary.status === 'failed' && (
          <div style={{ marginBottom: 16 }}>
            <Tag color="error" icon={<WarningOutlined />}>
              处理失败
            </Tag>
            {summary.error_message && (
              <div style={{ marginTop: 8 }}>
                <Text type="danger">{summary.error_message}</Text>
              </div>
            )}
          </div>
        )}
        
        <Tabs defaultActiveKey="summary">
          <TabPane 
            tab={<Space><FileTextOutlined />摘要</Space>} 
            key="summary"
          >
            {summary.summary_text ? (
              <div className="markdown-content">
                <ReactMarkdown>{summary.summary_text}</ReactMarkdown>
              </div>
            ) : (
              <Empty 
                description={summary.status === 'completed' ? 
                  "摘要为空" : 
                  summary.status === 'failed' ? 
                    "摘要生成失败" : 
                    "摘要正在生成中..."
                } 
              />
            )}
          </TabPane>
          
          <TabPane 
            tab={<Space><PictureOutlined />关键帧</Space>} 
            key="keyframes"
          >
            {renderKeyframes()}
          </TabPane>
          
          {summary.audio_transcript && (
            <TabPane 
              tab={<Space><FileTextOutlined />音频转录</Space>} 
              key="transcript"
            >
              <div style={{ whiteSpace: 'pre-line', padding: 16, background: '#fafafa', borderRadius: 4 }}>
                {summary.audio_transcript}
              </div>
            </TabPane>
          )}
          
          <TabPane 
            tab={<Space><InfoCircleOutlined />元数据</Space>} 
            key="metadata"
          >
            {renderMetadata()}
          </TabPane>
        </Tabs>
        
        <Divider />
        
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <Text type="secondary">创建时间: {formatDate(summary.created_at)}</Text>
          {summary.updated_at && (
            <Text type="secondary">更新时间: {formatDate(summary.updated_at)}</Text>
          )}
        </div>
      </Card>
    </div>
  );
};

export default SummaryDetail; 