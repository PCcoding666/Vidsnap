import React, { useState } from 'react';
import { Form, Input, Button, Select, Switch, Slider, Card, Divider, Tooltip, Space } from 'antd';
import { YoutubeOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons';
import { createSummary } from '../services/summaryService';

const { Option } = Select;

const SummaryForm = ({ onSuccess, locale }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [advancedMode, setAdvancedMode] = useState(false);
  const [keyframeMethod, setKeyframeMethod] = useState('uniform');

  // 根据当前语言环境选择的默认语言
  const getDefaultLanguage = () => {
    return locale || 'zh';
  };

  // 表单提交处理
  const handleSubmit = async (values) => {
    setLoading(true);
    try {
      const response = await createSummary(values);
      form.resetFields();
      if (onSuccess) {
        onSuccess(response);
      }
    } catch (error) {
      console.error('创建摘要失败', error);
    } finally {
      setLoading(false);
    }
  };

  // 语言选项
  const languageOptions = [
    { value: 'zh', label: '中文' },
    { value: 'en', label: 'English' },
    { value: 'ko', label: '한국어' }
  ];

  // 摘要粒度选项
  const granularityOptions = [
    { value: 'short', label: '简短', description: '生成不超过200字的简短摘要' },
    { value: 'medium', label: '中等', description: '包含主要内容、关键点和结论的摘要' },
    { value: 'detailed', label: '详细', description: '尽可能详细地描述视频内容' }
  ];

  // 关键帧提取方法选项
  const keyframeMethodOptions = [
    { value: 'uniform', label: '均匀分段', description: '在视频中均匀提取关键帧' },
    { value: 'interval', label: '固定间隔', description: '按固定时间间隔提取关键帧' },
    { value: 'scene', label: '场景检测', description: '根据视频场景变化提取关键帧' }
  ];

  return (
    <Card 
      title="创建视频摘要" 
      extra={
        <Tooltip title={advancedMode ? "隐藏高级选项" : "显示高级选项"}>
          <Button 
            type="text" 
            icon={<SettingOutlined />} 
            onClick={() => setAdvancedMode(!advancedMode)}
          />
        </Tooltip>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{
          video_url: '',
          language: getDefaultLanguage(),
          granularity: 'medium',
          use_audio: true,
          speaker_diarization: false,
          keyframe_method: 'uniform',
          num_frames: 5,
          interval_seconds: 10
        }}
      >
        {/* YouTube URL输入 */}
        <Form.Item
          name="video_url"
          label="YouTube 视频链接"
          rules={[{ required: true, message: '请输入YouTube视频链接' }]}
        >
          <Input 
            prefix={<YoutubeOutlined style={{ color: 'red' }} />} 
            placeholder="https://www.youtube.com/watch?v=..." 
          />
        </Form.Item>

        {/* 语言选择 */}
        <Form.Item
          name="language"
          label="输出语言"
        >
          <Select>
            {languageOptions.map(option => (
              <Option key={option.value} value={option.value}>{option.label}</Option>
            ))}
          </Select>
        </Form.Item>

        {/* 摘要粒度 */}
        <Form.Item
          name="granularity"
          label={
            <Space>
              摘要粒度
              <Tooltip title="选择生成摘要的详细程度">
                <QuestionCircleOutlined />
              </Tooltip>
            </Space>
          }
        >
          <Select>
            {granularityOptions.map(option => (
              <Option key={option.value} value={option.value}>
                {option.label} - {option.description}
              </Option>
            ))}
          </Select>
        </Form.Item>

        {/* 高级选项 */}
        {advancedMode && (
          <>
            <Divider>高级选项</Divider>

            {/* 使用音频转录 */}
            <Form.Item
              name="use_audio"
              label="使用音频转录"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>

            {/* 说话人分离 (仅当使用音频转录时可用) */}
            <Form.Item
              name="speaker_diarization"
              label={
                <Space>
                  说话人分离
                  <Tooltip title="识别不同的说话人并在转录中标记">
                    <QuestionCircleOutlined />
                  </Tooltip>
                </Space>
              }
              valuePropName="checked"
              dependencies={['use_audio']}
            >
              <Switch disabled={!form.getFieldValue('use_audio')} />
            </Form.Item>

            {/* 关键帧提取方法 */}
            <Form.Item
              name="keyframe_method"
              label="关键帧提取方法"
            >
              <Select onChange={setKeyframeMethod}>
                {keyframeMethodOptions.map(option => (
                  <Option key={option.value} value={option.value}>
                    {option.label} - {option.description}
                  </Option>
                ))}
              </Select>
            </Form.Item>

            {/* 关键帧数量 (仅在均匀分段和场景检测方法时可用) */}
            {keyframeMethod === 'uniform' && (
              <Form.Item
                name="num_frames"
                label="关键帧数量"
              >
                <Slider min={1} max={20} marks={{ 1: '1', 5: '5', 10: '10', 20: '20' }} />
              </Form.Item>
            )}

            {/* 时间间隔 (仅在固定间隔方法时可用) */}
            {keyframeMethod === 'interval' && (
              <Form.Item
                name="interval_seconds"
                label="时间间隔(秒)"
              >
                <Slider min={1} max={60} marks={{ 1: '1秒', 10: '10秒', 30: '30秒', 60: '1分钟' }} />
              </Form.Item>
            )}
          </>
        )}

        {/* 提交按钮 */}
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            生成摘要
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
};

export default SummaryForm; 