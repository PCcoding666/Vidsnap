import React, { useState, useEffect } from 'react';
import { Row, Col, Card, Typography, Space, Divider, Empty, Spin, Alert, message } from 'antd';
import { PlayCircleOutlined, HistoryOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import SummaryForm from '../components/SummaryForm';
import SummaryCard from '../components/SummaryCard';
import { getSummaries } from '../services/summaryService';
import { getSubscriptionStatus } from '../services/subscriptionService';

const { Title, Text } = Typography;

const Dashboard = ({ user, locale }) => {
  const [recentSummaries, setRecentSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [subscription, setSubscription] = useState(null);
  const navigate = useNavigate();

  // 加载最近的摘要和订阅状态
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [summariesData, subscriptionData] = await Promise.all([
          getSummaries(),
          getSubscriptionStatus()
        ]);
        
        // 最近的5个摘要
        const recent = summariesData
          .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
          .slice(0, 5);
        
        setRecentSummaries(recent);
        setSubscription(subscriptionData);
      } catch (error) {
        console.error('获取数据失败', error);
        message.error('获取数据失败: ' + error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // 处理创建摘要成功
  const handleSummaryCreated = (summary) => {
    message.success('摘要任务已提交，正在处理中');
    setRecentSummaries(prev => [summary, ...prev.slice(0, 4)]);
    // 刷新订阅状态
    getSubscriptionStatus().then(data => setSubscription(data));
  };

  // 渲染用量统计
  const renderUsageStats = () => {
    if (!subscription) return null;
    
    const { videos_per_month, videos_processed, plan, plan_name } = subscription;
    const usagePercent = (videos_processed / videos_per_month) * 100;
    
    return (
      <Card style={{ marginBottom: 24 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text>当前订阅: {plan_name}</Text>
            <Text 
              type={usagePercent > 80 ? 'danger' : usagePercent > 50 ? 'warning' : ''}
              strong
            >
              已使用 {videos_processed}/{videos_per_month} 次
            </Text>
          </div>
          
          <div 
            style={{ 
              height: 8, 
              background: '#f0f0f0', 
              borderRadius: 4,
              overflow: 'hidden',
              marginTop: 8
            }}
          >
            <div 
              style={{ 
                height: '100%', 
                width: `${Math.min(usagePercent, 100)}%`,
                background: usagePercent > 80 ? '#ff4d4f' : usagePercent > 50 ? '#faad14' : '#52c41a',
                borderRadius: 4
              }}
            />
          </div>
          
          {usagePercent > 80 && (
            <Alert 
              message="您的使用次数即将用完" 
              description="请考虑升级订阅计划以获取更多使用次数。" 
              type="warning" 
              showIcon 
              action={
                <Text.Link onClick={() => navigate('/subscription')}>
                  升级订阅
                </Text.Link>
              }
            />
          )}
        </Space>
      </Card>
    );
  };

  return (
    <div>
      <Row gutter={24}>
        <Col xs={24} lg={12}>
          <Title level={4}>
            <PlayCircleOutlined /> 创建新摘要
          </Title>
          
          {renderUsageStats()}
          
          <SummaryForm 
            onSuccess={handleSummaryCreated}
            locale={locale}
          />
        </Col>
        
        <Col xs={24} lg={12}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <Title level={4}>
              <HistoryOutlined /> 最近的摘要
            </Title>
            
            <Text.Link onClick={() => navigate('/history')}>
              查看全部
            </Text.Link>
          </div>
          
          {loading ? (
            <div style={{ textAlign: 'center', padding: 48 }}>
              <Spin size="large" />
            </div>
          ) : recentSummaries.length > 0 ? (
            <div>
              {recentSummaries.map(summary => (
                <SummaryCard 
                  key={summary.id} 
                  summary={summary}
                  onDelete={(id) => {
                    setRecentSummaries(prev => prev.filter(s => s.id !== id));
                  }}
                  onUpdate={(updated) => {
                    setRecentSummaries(prev => 
                      prev.map(s => s.id === updated.id ? updated : s)
                    );
                  }}
                />
              ))}
            </div>
          ) : (
            <Empty 
              description="暂无摘要记录" 
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard; 