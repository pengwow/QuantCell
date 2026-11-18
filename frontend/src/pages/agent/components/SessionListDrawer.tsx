/**
 * 会话列表抽屉 —— 自 Agent.tsx 原样拆出（P1 工作台改造，仅文件移动不改语义）。
 */
import { Drawer, Tooltip, Button, Dropdown } from 'antd';
import { PlusOutlined, ClearOutlined, DeleteOutlined, MoreOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Session } from '../store/agentStore';
import { QUANT_COLORS } from '@/utils/colors';

interface SessionListDrawerProps {
  visible: boolean;
  onClose: () => void;
  sessions: Session[];
  currentSessionId: string;
  onSwitchSession: (sessionId: string) => void;
  onCreateSession: () => void;
  onClearSession: () => void;
  onDeleteSession: (sessionId: string, e: React.MouseEvent) => void;
}

const SessionListDrawer = ({
  visible,
  onClose,
  sessions,
  currentSessionId,
  onSwitchSession,
  onCreateSession,
  onClearSession,
  onDeleteSession,
}: SessionListDrawerProps) => {
  const { t } = useTranslation();
  return (
    <Drawer
      title={t('agent_session_history')}
      placement="right"
      onClose={onClose}
      open={visible}
      size="default"
      className="session-drawer"
      extra={
        <Tooltip title={t('agent_new_session')}>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={onCreateSession}
          />
        </Tooltip>
      }
    >
      <div className="session-list">
        {sessions.map(session => (
          <Tooltip
            key={session.id}
            title={new Date(session.updatedAt).toLocaleString()}
            placement="left"
          >
            <div
              className={`session-item ${session.id === currentSessionId ? 'active' : ''}`}
              onClick={() => {
                onSwitchSession(session.id);
                onClose();
              }}
            >
              <span className="session-name-text">{session.name}</span>
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'clear',
                      label: t('agent_clear_messages'),
                      icon: <ClearOutlined />,
                      onClick: (e) => {
                        e.domEvent.stopPropagation();
                        onClearSession();
                      },
                    },
                    {
                      key: 'delete',
                      label: (
                        <span style={{ color: QUANT_COLORS.negative }}>
                          <DeleteOutlined /> {t('agent_delete_session')}
                        </span>
                      ),
                      danger: true,
                      onClick: (e) => {
                        e.domEvent.stopPropagation();
                        onDeleteSession(session.id, e.domEvent as React.MouseEvent);
                      },
                    },
                  ],
                }}
                trigger={['click']}
              >
                <Button
                  type="text"
                  size="small"
                  icon={<MoreOutlined />}
                  onClick={(e) => e.stopPropagation()}
                  className="session-more-btn"
                />
              </Dropdown>
            </div>
          </Tooltip>
        ))}
      </div>
    </Drawer>
  );
};

export default SessionListDrawer;
