import React, { useState, useEffect } from 'react';
import { 
  Row, 
  Col, 
  Card, 
  Typography, 
  Button, 
  Descriptions, 
  Tag, 
  Spin, 
  Modal, 
  Radio, 
  Alert,
  message,
  List,
  Result
} from 'antd';
import { 
  CrownOutlined, 
  CheckCircleOutlined, 
  RocketOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { getSubscriptionStatus, getSubscriptionPlans, createSubscription, cancelSubscription } from '../services/subscriptionService';

const { Title, Text, Paragraph } = Typography;

const Subscription = ({ user, locale }) => {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState(null);
  const [plans, setPlans] = useState([]);
  const [upgradeModalVisible, setUpgradeModalVisible] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [cancelModalVisible, setCancelModalVisible] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState('stripe');
  const [processing, setProcessing] = useState(false);
  const [success, setSuccess] = useState(false);

  // 加载订阅状态和计划
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [statusData, plansData] = await Promise.all([
          getSubscriptionStatus(),
          getSubscriptionPlans()
        ]);
        setStatus(statusData);
        setPlans(plansData);
      } catch (error) {
        console.error('获取订阅数据失败', error);
        message.error('获取订阅数据失败: ' + error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // 处理升级订阅
  const handleUpgrade = async () => {
    if (!selectedPlan) {
      message.warning('请选择订阅计划');
      return;
    }

    setProcessing(true);
    try {
      await createSubscription({
        plan: selectedPlan,
        payment_method: paymentMethod
      });
      
      // 刷新订阅状态
      const newStatus = await getSubscriptionStatus();
      setStatus(newStatus);
      
      setSuccess(true);
      message.success('订阅计划已更新');
    } catch (error) {
      console.error('更新订阅失败', error);
      message.error('更新订阅失败: ' + error);
    } finally {
      setProcessing(false);
    }
  };

  // 处理取消订阅
  const handleCancel = async () => {
    setProcessing(true);
    try {
      await cancelSubscription();
      
      // 刷新订阅状态
      const newStatus = await getSubscriptionStatus();
      setStatus(newStatus);
      
      setCancelModalVisible(false);
      message.success('订阅已取消');
    } catch (error) {
      console.error('取消订阅失败', error);
      message.error('取消订阅失败: ' + error);
    } finally {
      setProcessing(false);
    }
  };

  // 渲染订阅状态
  const renderSubscriptionStatus = () => {
    if (!status) return null;

    const { plan, plan_name, videos_per_month, videos_processed, subscription_active, expires_at } = status;
    const usagePercent = (videos_processed / videos_per_month) * 100;

    return (
      <Card title="当前订阅" style={{ marginBottom: 24 }}>
        <Descriptions bordered column={{ xs: 1, sm: 2 }}>
          <Descriptions.Item label="订阅计划">
            {plan_name} {plan !== 'free' && <CrownOutlined style={{ color: '#faad14' }} />}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            {subscription_active ? (
              <Tag color="success">已激活</Tag>
            ) : (
              <Tag color="default">免费版</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="使用情况">
            <div>
              <div style={{ marginBottom: 8 }}>
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
                  overflow: 'hidden'
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
            </div>
          </Descriptions.Item>
          {subscription_active && expires_at && (
            <Descriptions.Item label="到期时间">
              {new Date(expires_at).toLocaleDateString()}
            </Descriptions.Item>
          )}
        </Descriptions>

        <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
          <Button 
            type="primary" 
            onClick={() => {
              setSelectedPlan(null);
              setSuccess(false);
              setUpgradeModalVisible(true);
            }}
          >
            升级订阅
          </Button>
          {plan !== 'free' && (
            <Button 
              danger 
              style={{ marginLeft: 16 }} 
              onClick={() => setCancelModalVisible(true)}
            >
              取消订阅
            </Button>
          )}
        </div>
      </Card>
    );
  };

  // 渲染计划卡片
  const renderPlanCard = (plan) => {
    const { id, name, price, videos_per_month, features } = plan;
    const isCurrent = status && status.plan === id;
    const isSelected = selectedPlan === id;

    return (
      <Card 
        className={`subscription-card ${isSelected ? 'highlight' : ''}`}
        hoverable
        style={{ 
          borderColor: isSelected ? '#1890ff' : isCurrent ? '#52c41a' : '#f0f0f0',
          cursor: 'pointer'
        }}
        onClick={() => setSelectedPlan(id)}
      >
        <div className="subscription-header">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={4} style={{ margin: 0 }}>
              {name} {id !== 'free' && <CrownOutlined style={{ color: '#faad14' }} />}
            </Title>
            {isCurrent && (
              <Tag color="success">当前计划</Tag>
            )}
          </div>
          <div className="subscription-price">
            {price > 0 ? `$${price.toFixed(2)}/月` : '免费'}
          </div>
          <div>
            <Tag color="processing">{videos_per_month} 次/月</Tag>
          </div>
        </div>
        
        <div className="subscription-features">
          <List
            itemLayout="horizontal"
            dataSource={features}
            renderItem={item => (
              <List.Item>
                <List.Item.Meta
                  avatar={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                  title={item}
                />
              </List.Item>
            )}
          />
        </div>
      </Card>
    );
  };

  // 渲染升级模态框
  const renderUpgradeModal = () => {
    if (success) {
      return (
        <Modal
          title="订阅成功"
          visible={upgradeModalVisible}
          footer={[
            <Button key="close" type="primary" onClick={() => setUpgradeModalVisible(false)}>
              关闭
            </Button>
          ]}
          onCancel={() => setUpgradeModalVisible(false)}
        >
          <Result
            status="success"
            title="订阅计划已更新"
            subTitle="您的订阅计划已成功更新，现在您可以享受更多功能。"
          />
        </Modal>
      );
    }

    return (
      <Modal
        title="升级订阅"
        visible={upgradeModalVisible}
        onCancel={() => setUpgradeModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setUpgradeModalVisible(false)}>
            取消
          </Button>,
          <Button 
            key="upgrade" 
            type="primary" 
            loading={processing}
            disabled={!selectedPlan} 
            onClick={handleUpgrade}
          >
            确认支付
          </Button>
        ]}
        width={700}
      >
        <div style={{ marginBottom: 24 }}>
          <Title level={5}>选择订阅计划</Title>
          <Row gutter={16}>
            {plans.map(plan => (
              <Col xs={24} md={8} key={plan.id}>
                {renderPlanCard(plan)}
              </Col>
            ))}
          </Row>
        </div>

        {selectedPlan && selectedPlan !== 'free' && (
          <>
            <Divider />
            <div style={{ marginBottom: 24 }}>
              <Title level={5}>选择支付方式</Title>
              <Radio.Group 
                value={paymentMethod} 
                onChange={e => setPaymentMethod(e.target.value)}
              >
                <Radio value="stripe">信用卡 (Stripe)</Radio>
                <Radio value="paypal">PayPal</Radio>
              </Radio.Group>
            </div>
            
            <Alert
              message="模拟支付"
              description="这是一个模拟的支付流程，不会产生实际收费。在真实环境中，您将被重定向到安全的支付页面。"
              type="info"
              showIcon
            />
          </>
        )}
      </Modal>
    );
  };

  // 渲染取消订阅模态框
  const renderCancelModal = () => {
    return (
      <Modal
        title="取消订阅"
        visible={cancelModalVisible}
        onCancel={() => setCancelModalVisible(false)}
        footer={[
          <Button key="back" onClick={() => setCancelModalVisible(false)}>
            返回
          </Button>,
          <Button 
            key="cancel" 
            type="primary" 
            danger 
            loading={processing}
            onClick={handleCancel}
          >
            确认取消
          </Button>
        ]}
      >
        <Alert
          message="确认取消订阅？"
          description="取消订阅后，您将不再享受高级功能，但可以继续使用免费版的功能。当前订阅周期结束后，您的账户将自动降级为免费版。"
          type="warning"
          showIcon
        />
      </Modal>
    );
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={4}>
          <CrownOutlined /> 订阅管理
        </Title>
        <Paragraph>
          升级订阅计划，享受更多功能和更高的使用配额
        </Paragraph>
      </div>
      
      {renderSubscriptionStatus()}
      
      <Card title="可用订阅计划">
        <Row gutter={16}>
          {plans.map(plan => (
            <Col xs={24} md={8} key={plan.id}>
              {renderPlanCard(plan)}
              <div style={{ textAlign: 'center', marginTop: 16 }}>
                <Button 
                  type={plan.id === status?.plan ? 'default' : 'primary'}
                  disabled={plan.id === status?.plan}
                  onClick={() => {
                    setSelectedPlan(plan.id);
                    setSuccess(false);
                    setUpgradeModalVisible(true);
                  }}
                >
                  {plan.id === status?.plan ? '当前计划' : '选择此计划'}
                </Button>
              </div>
            </Col>
          ))}
        </Row>
      </Card>
      
      {renderUpgradeModal()}
      {renderCancelModal()}
    </div>
  );
};

export default Subscription; 