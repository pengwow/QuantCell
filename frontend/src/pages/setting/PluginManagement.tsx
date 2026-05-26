import { useState } from 'react';
import {
  Alert,
  App,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd';
import {
  CloudUploadOutlined,
  DeleteOutlined,
  GithubOutlined,
  InfoCircleOutlined,
  LoadingOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { pluginApi, type PluginInfo, type PluginStatus } from '@/api/plugin';
import { usePlugins } from '@/plugins';

const { Text, Paragraph } = Typography;

const STATUS_CONFIG: Record<PluginStatus, { color: string; text: string }> = {
  installed: { color: 'default', text: '已安装' },
  enabled: { color: 'success', text: '运行中' },
  disabled: { color: 'warning', text: '已停止' },
  pending_restart: { color: 'processing', text: '待重启' },
  error: { color: 'error', text: '错误' },
};

export default function PluginManagement() {
  const { plugins, loading, refresh, enablePlugin, disablePlugin } = usePlugins();
  const { message } = App.useApp();

  const [installOpen, setInstallOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedPlugin, setSelectedPlugin] = useState<PluginInfo | null>(null);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});

  const [installTab, setInstallTab] = useState('zip');
  const [uploading, setUploading] = useState(false);
  const [gitForm] = Form.useForm();

  const hasPendingRestart = plugins.some((p) => p.status === 'pending_restart');

  const setPluginLoading = (name: string, val: boolean) =>
    setActionLoading((prev) => ({ ...prev, [name]: val }));

  const handleToggle = async (plugin: PluginInfo, checked: boolean) => {
    setPluginLoading(plugin.name, true);
    try {
      if (checked) {
        await enablePlugin(plugin.name);
      } else {
        await disablePlugin(plugin.name);
      }
    } finally {
      setPluginLoading(plugin.name, false);
    }
  };

  const handleUninstall = async (name: string) => {
    setPluginLoading(name, true);
    try {
      await pluginApi.uninstallPlugin(name);
      message.success(`插件 ${name} 已卸载`);
      await refresh();
    } catch (err) {
      message.error(`卸载失败: ${(err as Error).message}`);
    } finally {
      setPluginLoading(name, false);
    }
  };

  const handleZipUpload = async (file: File) => {
    setUploading(true);
    try {
      await pluginApi.installFromZip(file);
      message.success('插件安装成功');
      setInstallOpen(false);
      await refresh();
    } catch (err) {
      message.error(`安装失败: ${(err as Error).message}`);
    } finally {
      setUploading(false);
    }
    return false;
  };

  const handleGitInstall = async () => {
    try {
      const { url, branch } = await gitForm.validateFields();
      setUploading(true);
      await pluginApi.installFromGit(url, branch || undefined);
      message.success('插件安装成功');
      setInstallOpen(false);
      gitForm.resetFields();
      await refresh();
    } catch {
      // 表单校验失败时忽略
    } finally {
      setUploading(false);
    }
  };

  const openDetail = (plugin: PluginInfo) => {
    setSelectedPlugin(plugin);
    setDetailOpen(true);
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>插件管理</Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setInstallOpen(true)}>
            安装插件
          </Button>
        </Space>
      </div>

      {hasPendingRestart && (
        <Alert
          type="info"
          showIcon
          message="有插件需要重启后才能生效，请重启后端服务。"
          style={{ marginBottom: 16 }}
          closable
        />
      )}

      {plugins.length === 0 && !loading ? (
        <Empty description="暂无已安装插件" />
      ) : (
        <Row gutter={[16, 16]}>
          {plugins.map((plugin) => (
            <Col key={plugin.name} xs={24} sm={12} md={12} lg={8} xl={8} xxl={6}>
              <PluginCard
                plugin={plugin}
                loading={!!actionLoading[plugin.name]}
                onToggle={handleToggle}
                onUninstall={handleUninstall}
                onDetail={openDetail}
              />
            </Col>
          ))}
        </Row>
      )}

      <InstallModal
        open={installOpen}
        onClose={() => setInstallOpen(false)}
        tab={installTab}
        setTab={setInstallTab}
        uploading={uploading}
        onZipUpload={handleZipUpload}
        gitForm={gitForm}
        onGitInstall={handleGitInstall}
      />

      <DetailModal
        open={detailOpen}
        plugin={selectedPlugin}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  );
}

function PluginCard({
  plugin,
  loading,
  onToggle,
  onUninstall,
  onDetail,
}: {
  plugin: PluginInfo;
  loading: boolean;
  onToggle: (p: PluginInfo, checked: boolean) => void;
  onUninstall: (name: string) => void;
  onDetail: (p: PluginInfo) => void;
}) {
  const sc = STATUS_CONFIG[plugin.status] ?? STATUS_CONFIG.installed;

  return (
    <Card
      hoverable
      loading={loading}
      actions={[
        <Tooltip title="详情" key="info">
          <InfoCircleOutlined onClick={() => onDetail(plugin)} />
        </Tooltip>,
        <Popconfirm
          key="uninstall"
          title={`确定卸载插件「${plugin.name}」？`}
          onConfirm={() => onUninstall(plugin.name)}
          okText="卸载"
          cancelText="取消"
        >
          <Tooltip title="卸载">
            <DeleteOutlined />
          </Tooltip>
        </Popconfirm>,
      ]}
    >
      <Card.Meta
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text strong ellipsis style={{ maxWidth: 160 }}>{plugin.name}</Text>
            <Badge status={sc.color as any} text={<Text type="secondary" style={{ fontSize: 12 }}>{sc.text}</Text>} />
          </div>
        }
        description={
          <div>
            <Paragraph
              type="secondary"
              ellipsis={{ rows: 2 }}
              style={{ fontSize: 13, marginBottom: 8 }}
            >
              {plugin.description || '暂无描述'}
            </Paragraph>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Space size={4}>
                <Tag>{plugin.version}</Tag>
                <Tag color={plugin.load_type === 'hot' ? 'green' : 'blue'}>
                  {plugin.load_type === 'hot' ? '热加载' : '重启加载'}
                </Tag>
              </Space>
              <Switch
                size="small"
                checked={plugin.status === 'enabled'}
                disabled={plugin.status === 'pending_restart' || plugin.status === 'error'}
                onChange={(checked) => onToggle(plugin, checked)}
              />
            </div>
          </div>
        }
      />
    </Card>
  );
}

function InstallModal({
  open,
  onClose,
  tab,
  setTab,
  uploading,
  onZipUpload,
  gitForm,
  onGitInstall,
}: {
  open: boolean;
  onClose: () => void;
  tab: string;
  setTab: (t: string) => void;
  uploading: boolean;
  onZipUpload: (file: File) => Promise<boolean | void>;
  gitForm: ReturnType<typeof Form.useForm>[0];
  onGitInstall: () => void;
}) {
  return (
    <Modal
      title="安装插件"
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: 'zip',
            label: 'ZIP 上传',
            children: (
              <Upload.Dragger
                accept=".zip"
                maxCount={1}
                showUploadList={false}
                beforeUpload={(file) => {
                  onZipUpload(file);
                  return false;
                }}
                disabled={uploading}
              >
                <p style={{ fontSize: 40, color: '#ccc' }}>
                  {uploading ? <LoadingOutlined /> : <CloudUploadOutlined />}
                </p>
                <p>{uploading ? '正在安装...' : '点击或拖拽 ZIP 文件到此处'}</p>
              </Upload.Dragger>
            ),
          },
          {
            key: 'git',
            label: (
              <span><GithubOutlined /> Git URL</span>
            ),
            children: (
              <Form form={gitForm} layout="vertical">
                <Form.Item
                  name="url"
                  label="Git 仓库地址"
                  rules={[{ required: true, message: '请输入 Git URL' }]}
                >
                  <Input placeholder="https://github.com/user/plugin.git" />
                </Form.Item>
                <Form.Item name="branch" label="分支（可选）">
                  <Input placeholder="main" />
                </Form.Item>
                <Button type="primary" onClick={onGitInstall} loading={uploading} block>
                  安装
                </Button>
              </Form>
            ),
          },
        ]}
      />
    </Modal>
  );
}

function DetailModal({
  open,
  plugin,
  onClose,
}: {
  open: boolean;
  plugin: PluginInfo | null;
  onClose: () => void;
}) {
  if (!plugin) return null;
  const sc = STATUS_CONFIG[plugin.status] ?? STATUS_CONFIG.installed;

  return (
    <Modal
      title={`插件详情 — ${plugin.name}`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnHidden
    >
      <Descriptions column={2} bordered size="small">
        <Descriptions.Item label="名称">{plugin.name}</Descriptions.Item>
        <Descriptions.Item label="版本">{plugin.version}</Descriptions.Item>
        <Descriptions.Item label="作者">{plugin.author || '-'}</Descriptions.Item>
        <Descriptions.Item label="状态">
          <Badge status={sc.color as any} text={sc.text} />
        </Descriptions.Item>
        <Descriptions.Item label="加载方式">
          {plugin.load_type === 'hot' ? '热加载' : '重启加载'}
        </Descriptions.Item>
        <Descriptions.Item label="安装来源">{plugin.install_source}</Descriptions.Item>
        <Descriptions.Item label="描述" span={2}>
          {plugin.description || '暂无描述'}
        </Descriptions.Item>
        <Descriptions.Item label="权限" span={2}>
          {plugin.permissions?.length
            ? plugin.permissions.map((p) => <Tag key={p}>{p}</Tag>)
            : '无特殊权限'}
        </Descriptions.Item>
        <Descriptions.Item label="安装时间" span={2}>{plugin.installed_at}</Descriptions.Item>
      </Descriptions>

      {plugin.error_message && (
        <Alert
          type="error"
          showIcon
          message="错误信息"
          description={plugin.error_message}
          style={{ marginTop: 16 }}
        />
      )}

      {plugin.config_schema && (
        <div style={{ marginTop: 16 }}>
          <Typography.Title level={5}>配置 Schema</Typography.Title>
          <pre
            style={{
              background: '#f5f5f5',
              padding: 12,
              borderRadius: 6,
              maxHeight: 300,
              overflow: 'auto',
              fontSize: 12,
            }}
          >
            {JSON.stringify(plugin.config_schema, null, 2)}
          </pre>
        </div>
      )}
    </Modal>
  );
}
