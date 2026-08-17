/**
 * AgentPanel — Global AI assistant panel.
 *
 * Can be opened on any page with Cmd+K or click.
 * Passes page context to the backend for contextual assistance.
 */
import { useState, useCallback } from 'react';
import { Drawer, Input, Button, Space, Typography } from 'antd';
import { RobotOutlined, SendOutlined, CloseOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { TextArea } = Input;

export interface AgentPanelContext {
  page: string;
  selectedItem?: Record<string, unknown>;
  error?: string;
}

export interface AgentPanelProps {
  visible: boolean;
  onClose: () => void;
  context?: AgentPanelContext;
}

export default function AgentPanel({ visible, onClose, context }: AgentPanelProps) {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [loading, setLoading] = useState(false);

  const handleSend = useCallback(async () => {
    if (!message.trim()) return;

    const userMsg = message.trim();
    setMessage('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const response = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          context: context || {},
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setMessages(prev => [...prev, { role: 'assistant', content: data.content || data.message || '处理完成' }]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: '请求失败，请重试' }]);
      }
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '网络错误，请检查连接' }]);
    } finally {
      setLoading(false);
    }
  }, [message, context]);

  return (
    <Drawer
      title={
        <Space>
          <RobotOutlined />
          <span>AI 助手</span>
          {context?.page && <Text type="secondary">({context.page})</Text>}
        </Space>
      }
      placement="right"
      width={400}
      open={visible}
      onClose={onClose}
      extra={
        <Button type="text" icon={<CloseOutlined />} onClick={onClose} />
      }
      data-testid="agent-panel"
    >
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {messages.map((msg, i) => (
            <div
              key={i}
              style={{
                padding: '8px 12px',
                margin: '4px 0',
                borderRadius: 8,
                background: msg.role === 'user' ? '#e6f7ff' : '#f6ffed',
                textAlign: msg.role === 'user' ? 'right' : 'left',
              }}
            >
              {msg.content}
            </div>
          ))}
        </div>

        <Space.Compact style={{ width: '100%' }}>
          <TextArea
            value={message}
            onChange={e => setMessage(e.target.value)}
            placeholder="输入消息... (Enter发送)"
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={e => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={loading}
          />
        </Space.Compact>
      </div>
    </Drawer>
  );
}
