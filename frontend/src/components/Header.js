import React from 'react';
import { Layout, Menu } from 'antd';
import { Link } from 'react-router-dom';

const { Header: AntHeader } = Layout;

const Header = () => {
  return (
    <AntHeader style={{ background: '#fff', borderBottom: '1px solid #f0f0f0' }}>
      <div style={{ float: 'left', marginRight: '20px' }}>
        <h1 style={{ margin: '0', fontSize: '20px', lineHeight: '64px' }}>
          YouTube 视频摘要
        </h1>
      </div>
      <Menu mode="horizontal" defaultSelectedKeys={['home']}>
        <Menu.Item key="home">
          <Link to="/">首页</Link>
        </Menu.Item>
        <Menu.Item key="history">
          <Link to="/history">历史记录</Link>
        </Menu.Item>
      </Menu>
    </AntHeader>
  );
};

export default Header; 