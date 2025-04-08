import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, message, Divider } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { login } from '../services/authService';

const { Title, Text } = Typography;

const Login = ({ onLogin }) => {
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (values) => {
    setLoading(true);
    try {
      const response = await login(values.email, values.password);
      message.success('登录成功');
      
      // 获取 token 和用户数据，并调用父组件的 onLogin 回调
      const { access_token } = response;
      
      // 从 token 中获取的用户数据是有限的，通常完整的用户数据会在后续调用 /auth/me 获取
      if (onLogin) {
        // 这里先用简单的用户对象代替，实际应用中应该调用 getUser 获取完整用户数据
        const userData = { email: values.email, username: values.email.split('@')[0] };
        onLogin(userData, access_token);
      }
    } catch (error) {
      message.error('登录失败: ' + error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: '40px auto' }}>
      <Card>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3}>YouTube 视频摘要工具</Title>
          <Text type="secondary">登录以使用所有功能</Text>
        </div>
        
        <Form
          name="login"
          initialValues={{ remember: true }}
          onFinish={handleSubmit}
        >
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入邮箱地址' },
              { type: 'email', message: '请输入有效的邮箱地址' }
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="邮箱地址" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>

        <Divider>或者</Divider>

        <div style={{ textAlign: 'center' }}>
          <Link to="/register">
            <Button type="default" block>
              注册新账号
            </Button>
          </Link>
        </div>
      </Card>
    </div>
  );
};

export default Login; 