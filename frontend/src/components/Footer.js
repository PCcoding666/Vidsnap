import React from 'react';
import { Layout } from 'antd';

const { Footer: AntFooter } = Layout;

const Footer = () => {
  return (
    <AntFooter style={{ textAlign: 'center', background: '#f0f2f5' }}>
      YouTube 视频摘要 ©{new Date().getFullYear()} Created by Your Name
    </AntFooter>
  );
};

export default Footer; 