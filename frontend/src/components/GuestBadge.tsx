/**
 * 访客标识组件
 * 用于在UI中显示当前用户是否为访客，并提供相关提示
 */
import { useMemo } from "react";
import { Tag, Tooltip, Alert, Button, message } from "antd";
import { IconUserCircle, IconLock } from "@tabler/icons-react";
import { useNavigate } from "react-router-dom";
import { isGuestUser, getCurrentUsername, getRestrictedFeatureMessage } from "../utils/roleManager";

/**
 * 访客标签组件
 * 在Header或用户信息区域显示访客标识
 */
export const GuestTag = () => {
  const isGuest = useMemo(() => isGuestUser(), []);
  const username = useMemo(() => getCurrentUsername(), []);

  if (!isGuest) {
    return <span>{username}</span>;
  }

  return (
    <Tooltip title="访客模式：部分功能受限">
      <Tag color="orange" icon={<IconUserCircle size={14} />}>
        访客
      </Tag>
    </Tooltip>
  );
};

/**
 * 访客限制提示组件
 * 在受限功能区域显示提示信息
 */
export const GuestRestrictionAlert = ({ featureName }: { featureName?: string }) => {
  const isGuest = useMemo(() => isGuestUser(), []);
  const navigate = useNavigate();

  if (!isGuest) {
    return null;
  }

  const handleLogin = () => {
    navigate("/login");
  };

  return (
    <Alert
      type="warning"
      showIcon
      icon={<IconLock size={18} />}
      title={featureName ? `${featureName}功能受限` : "功能受限"}
      description={
        <div>
          <p>{getRestrictedFeatureMessage()}</p>
          <Button type="primary" size="small" onClick={handleLogin}>
            去登录
          </Button>
        </div>
      }
      style={{ marginBottom: 16 }}
    />
  );
};

/**
 * 访客功能保护包装器
 * 如果用户是访客，显示提示信息；否则显示子组件
 */
export const GuestProtected = ({
  children,
  featureName,
}: {
  children: React.ReactNode;
  featureName?: string;
  requiredPermission?: string;
}) => {
  const isGuest = useMemo(() => isGuestUser(), []);

  if (isGuest) {
    return <GuestRestrictionAlert featureName={featureName} />;
  }

  return <>{children}</>;
};

/**
 * 访客按钮包装器
 * 如果用户是访客，点击按钮时显示提示；否则正常执行
 */
export const GuestProtectedButton = ({
  children,
  onClick,
  featureName,
  ...props
}: {
  children: React.ReactNode;
  onClick?: () => void;
  featureName?: string;
} & React.ComponentProps<typeof Button>) => {
  const isGuest = useMemo(() => isGuestUser(), []);

  const handleClick = () => {
    if (isGuest) {
      message.warning(getRestrictedFeatureMessage());
      return;
    }
    onClick?.();
  };

  return (
    <Tooltip title={isGuest ? getRestrictedFeatureMessage() : ""}>
      <Button {...props} onClick={handleClick} disabled={props.disabled || isGuest}>
        {children}
      </Button>
    </Tooltip>
  );
};

export default GuestTag;
