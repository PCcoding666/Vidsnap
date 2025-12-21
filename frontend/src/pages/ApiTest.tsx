import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { apiService } from '@/services/api';

/**
 * API 测试页面 - 用于验证前后端集成
 */
export default function ApiTest() {
  const [healthStatus, setHealthStatus] = useState<string>('');
  const [serviceStatus, setServiceStatus] = useState<any>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  // 测试健康检查
  const testHealthCheck = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await apiService.healthCheck();
      setHealthStatus(response.status);
    } catch (err: any) {
      setError(`健康检查失败: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // 测试服务状态
  const testServiceStatus = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await apiService.getServiceStatus();
      setServiceStatus(response);
    } catch (err: any) {
      setError(`服务状态查询失败: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <h1 className="text-3xl font-bold mb-6">前后端 API 集成测试</h1>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6">
        {/* 健康检查测试 */}
        <Card>
          <CardHeader>
            <CardTitle>健康检查 API</CardTitle>
            <CardDescription>
              测试后端服务是否正常运行 (GET /health)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <Button onClick={testHealthCheck} disabled={loading}>
                {loading ? '测试中...' : '测试健康检查'}
              </Button>
              {healthStatus && (
                <div className="px-4 py-2 bg-green-100 text-green-800 rounded">
                  状态: {healthStatus}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 服务状态测试 */}
        <Card>
          <CardHeader>
            <CardTitle>服务状态 API</CardTitle>
            <CardDescription>
              查询所有微服务的可用性状态 (GET /video/status)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <Button onClick={testServiceStatus} disabled={loading}>
                {loading ? '查询中...' : '查询服务状态'}
              </Button>
              
              {serviceStatus && (
                <div className="mt-4 p-4 bg-gray-50 rounded">
                  <h3 className="font-semibold mb-2">服务可用性:</h3>
                  <div className="space-y-2">
                    {Object.entries(serviceStatus.services || {}).map(([service, available]) => (
                      <div key={service} className="flex items-center gap-2">
                        <span className={`w-3 h-3 rounded-full ${available ? 'bg-green-500' : 'bg-red-500'}`} />
                        <span>{service}</span>
                        <span className="text-sm text-gray-500">
                          {available ? '可用' : '不可用'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 配置信息 */}
        <Card>
          <CardHeader>
            <CardTitle>配置信息</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex gap-2">
                <span className="font-semibold">后端 API:</span>
                <span className="text-gray-600">http://localhost:8000</span>
              </div>
              <div className="flex gap-2">
                <span className="font-semibold">前端地址:</span>
                <span className="text-gray-600">http://localhost:8080</span>
              </div>
              <div className="flex gap-2">
                <span className="font-semibold">跨域代理:</span>
                <span className="text-gray-600">/api/* → http://localhost:8000/*</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 测试说明 */}
        <Card>
          <CardHeader>
            <CardTitle>测试说明</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-sm">
              <div>
                <h4 className="font-semibold mb-1">✅ 成功标志:</h4>
                <ul className="list-disc list-inside text-gray-600 space-y-1">
                  <li>健康检查返回 "healthy" 状态</li>
                  <li>服务状态显示各服务可用性</li>
                  <li>没有跨域错误（CORS）</li>
                </ul>
              </div>
              
              <div>
                <h4 className="font-semibold mb-1">❌ 常见问题:</h4>
                <ul className="list-disc list-inside text-gray-600 space-y-1">
                  <li>网络错误: 检查后端服务是否启动（端口 8000）</li>
                  <li>CORS 错误: 检查后端 CORS 中间件配置</li>
                  <li>404 错误: 检查 API 端点路径是否正确</li>
                </ul>
              </div>

              <div>
                <h4 className="font-semibold mb-1">�� 启动服务:</h4>
                <div className="bg-gray-100 p-2 rounded font-mono text-xs">
                  <div>后端: ./start_backend.sh api</div>
                  <div>前端: cd frontend && npm run dev</div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
