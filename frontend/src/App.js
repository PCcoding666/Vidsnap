import React from 'react';
import { Layout } from 'antd';
import { Routes, Route, Navigate } from 'react-router-dom';
import Home from './pages/Home';
import History from './pages/History';
import Header from './components/Header';
import Footer from './components/Footer';

const { Content } = Layout;

function App() {
  return (
    <Layout className="app-layout">
      <Header />
      <Content className="app-content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/history" element={<History />} />
          {/* 添加更多路由 */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Content>
      <Footer />
    </Layout>
  );
}

export default App; 