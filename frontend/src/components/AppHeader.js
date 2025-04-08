import React from 'react';
import { Layout, Menu, Button, Dropdown, Space, Avatar, Select } from 'antd';
import { UserOutlined, LogoutOutlined, SettingOutlined, TranslationOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Header } = Layout;
const { Option } = Select;

const AppHeader = ({ user, onLogout, locale, onChangeLocale }) => {
  const navigate = useNavigate();

  // 用户菜单项
  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
      onClick: () => navigate('/profile')
    },
    {
      key: 'subscription',
      icon: <SettingOutlined />,
      label: '订阅管理',
      onClick: () => navigate('/subscription')
    },
    {
      type: 'divider'
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: onLogout
    }
  ];

  return (
    <Header className="site-layout-background" style={{ padding: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <div style={{ flex: 1 }} />
      
      <div style={{ marginRight: 20, display: 'flex', alignItems: 'center' }}>
        {/* 语言选择器 */}
        <Select
          defaultValue={locale}
          style={{ width: 100, marginRight: 16 }}
          onChange={onChangeLocale}
          dropdownMatchSelectWidth={false}
        >
          <Option value="zh">中文</Option>
          <Option value="en">English</Option>
          <Option value="ko">한국어</Option>
        </Select>
        
        {user ? (
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <Button type="text">
              <Space>
                <Avatar icon={<UserOutlined />} />
                {user.username}
              </Space>
            </Button>
          </Dropdown>
        ) : (
          <Button type="primary" onClick={() => navigate('/login')}>
            登录
          </Button>
        )}
      </div>
    </Header>
  );
};

export default AppHeader; 