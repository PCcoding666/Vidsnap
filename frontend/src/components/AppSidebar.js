import React, { useState } from 'react';
import { Layout, Menu } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import { 
  HomeOutlined, 
  HistoryOutlined,
  CrownOutlined,
  UserOutlined,
  PlayCircleOutlined
} from '@ant-design/icons';

const { Sider } = Layout;

const AppSidebar = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  // 获取当前活动菜单项
  const getSelectedKey = () => {
    const path = location.pathname;
    if (path.startsWith('/dashboard')) return ['dashboard'];
    if (path.startsWith('/summary')) return ['dashboard'];
    if (path.startsWith('/history')) return ['history'];
    if (path.startsWith('/subscription')) return ['subscription'];
    if (path.startsWith('/profile')) return ['profile'];
    return ['dashboard'];
  };

  // 菜单项配置
  const menuItems = [
    {
      key: 'dashboard',
      icon: <HomeOutlined />,
      label: '首页',
      onClick: () => navigate('/dashboard')
    },
    {
      key: 'history',
      icon: <HistoryOutlined />,
      label: '历史记录',
      onClick: () => navigate('/history')
    },
    {
      key: 'subscription',
      icon: <CrownOutlined />,
      label: '订阅管理',
      onClick: () => navigate('/subscription')
    },
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
      onClick: () => navigate('/profile')
    }
  ];

  return (
    <Sider 
      collapsible 
      collapsed={collapsed} 
      onCollapse={setCollapsed}
      width={200}
      className="site-layout-background"
    >
      <div className="logo">
        {collapsed ? <PlayCircleOutlined /> : 'YouTube 摘要'}
      </div>
      <Menu
        mode="inline"
        selectedKeys={getSelectedKey()}
        style={{ height: '100%', borderRight: 0 }}
        items={menuItems}
      />
    </Sider>
  );
};

export default AppSidebar; 