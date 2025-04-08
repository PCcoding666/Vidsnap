import React from 'react';
import { 
  Card, 
  Typography, 
  Descriptions, 
  Avatar, 
  Badge, 
  Divider,
  Space
} from 'antd';
import { 
  UserOutlined, 
  MailOutlined, 
  CalendarOutlined, 
  CrownOutlined
} from '@ant-design/icons';

const { Title, Text } = Typography;

const UserProfile = ({ user, locale }) => {
  if (!user) {
    return null;
  }

  // 格式化日期
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString();
  };

  // 订阅计划映射
  const planMapping = {
    free: { name: '免费版', color: 'default' },
    basic: { name: '基础版', color: 'blue' },
    premium: { name: '高级版', color: 'gold' }
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={4}>
          <UserOutlined /> 个人资料
        </Title>
        <Text type="secondary">查看和管理您的账户信息</Text>
      </div>
      
      <Card>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Avatar size={80} icon={<UserOutlined />} />
          <Title level={3} style={{ marginTop: 16, marginBottom: 0 }}>
            {user.username}
          </Title>
          <Space>
            <Badge 
              status={user.is_active ? 'success' : 'default'} 
              text={user.is_active ? '已激活' : '未激活'} 
            />
            {user.subscription_plan !== 'free' && (
              <Badge 
                color={planMapping[user.subscription_plan]?.color || 'blue'} 
                text={
                  <Space>
                    <CrownOutlined />
                    {planMapping[user.subscription_plan]?.name || user.subscription_plan}
                  </Space>
                } 
              />
            )}
          </Space>
        </div>
        
        <Divider />
        
        <Descriptions bordered column={{ xs: 1, sm: 2 }}>
          <Descriptions.Item label={<Space><UserOutlined /> 用户名</Space>}>
            {user.username}
          </Descriptions.Item>
          
          <Descriptions.Item label={<Space><MailOutlined /> 邮箱</Space>}>
            {user.email}
          </Descriptions.Item>
          
          <Descriptions.Item label={<Space><CalendarOutlined /> 注册时间</Space>}>
            {formatDate(user.created_at)}
          </Descriptions.Item>
          
          <Descriptions.Item label={<Space><CrownOutlined /> 订阅计划</Space>}>
            {planMapping[user.subscription_plan]?.name || user.subscription_plan}
          </Descriptions.Item>
        </Descriptions>
        
        <Divider />
        
        <div>
          <Title level={5}>使用统计</Title>
          <Descriptions bordered column={1}>
            <Descriptions.Item label="本月已处理视频数">
              {user.usage?.videos_processed || 0}
            </Descriptions.Item>
            <Descriptions.Item label="上次计数重置时间">
              {formatDate(user.usage?.last_reset)}
            </Descriptions.Item>
          </Descriptions>
        </div>
      </Card>
    </div>
  );
};

export default UserProfile; 