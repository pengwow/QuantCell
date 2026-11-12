"""
RBAC权限控制模块单元测试

测试 rbac 模块的基于角色的访问控制功能。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-05-09
"""

import asyncio
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from utils.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    UserRole,
    check_permission,
    get_current_user_id,
    get_current_user_info,
    get_user_role_from_token,
    is_guest_user,
    require_permission,
    require_permission_sync,
)


class TestUserRole:
    """测试用户角色枚举"""

    def test_role_values(self):
        """测试角色值"""
        assert UserRole.GUEST.value == "guest"
        assert UserRole.USER.value == "user"
        assert UserRole.ADMIN.value == "admin"

    def test_role_from_string(self):
        """测试从字符串创建角色"""
        assert UserRole("guest") == UserRole.GUEST
        assert UserRole("user") == UserRole.USER
        assert UserRole("admin") == UserRole.ADMIN

    def test_invalid_role_raises(self):
        """测试无效角色抛出异常"""
        with pytest.raises(ValueError):
            UserRole("invalid_role")


class TestPermission:
    """测试权限枚举"""

    def test_permission_values(self):
        """测试权限值"""
        assert Permission.CONFIG_READ.value == "config:read"
        assert Permission.CONFIG_WRITE.value == "config:write"
        assert Permission.STRATEGY_READ.value == "strategy:read"
        assert Permission.DATA_WRITE.value == "data:write"

    def test_all_permissions_defined(self):
        """测试所有权限都已定义"""
        categories = [
            "config",
            "user",
            "strategy",
            "indicator",
            "backtest",
            "data",
            "ai",
            "log",
            "exchange",
            "worker",
        ]
        for category in categories:
            assert hasattr(Permission, f"{category.upper()}_READ")
        assert hasattr(Permission, "CONFIG_WRITE")
        assert hasattr(Permission, "USER_WRITE")


class TestRolePermissions:
    """测试角色权限映射"""

    def test_guest_permissions(self):
        """测试访客权限"""
        guest_perms = ROLE_PERMISSIONS[UserRole.GUEST]
        assert Permission.CONFIG_READ in guest_perms
        assert Permission.STRATEGY_READ in guest_perms
        assert Permission.CONFIG_WRITE not in guest_perms
        assert Permission.DATA_WRITE not in guest_perms

    def test_user_permissions(self):
        """测试普通用户权限"""
        user_perms = ROLE_PERMISSIONS[UserRole.USER]
        assert Permission.CONFIG_READ in user_perms
        assert Permission.CONFIG_WRITE in user_perms
        assert Permission.DATA_READ in user_perms
        assert Permission.DATA_WRITE in user_perms

    def test_admin_permissions(self):
        """测试管理员权限"""
        admin_perms = ROLE_PERMISSIONS[UserRole.ADMIN]
        assert Permission.CONFIG_READ in admin_perms
        assert Permission.CONFIG_WRITE in admin_perms
        assert Permission.USER_READ in admin_perms
        assert Permission.USER_WRITE in admin_perms
        assert len(admin_perms) == len(Permission)


class TestCheckPermission:
    """测试 check_permission 函数"""

    def test_guest_has_read_permissions(self):
        """测试访客有读权限"""
        assert check_permission(UserRole.GUEST, Permission.CONFIG_READ) is True
        assert check_permission(UserRole.GUEST, Permission.STRATEGY_READ) is True
        assert check_permission(UserRole.GUEST, Permission.DATA_READ) is True

    def test_guest_no_write_permissions(self):
        """测试访客无写权限"""
        assert check_permission(UserRole.GUEST, Permission.CONFIG_WRITE) is False
        assert check_permission(UserRole.GUEST, Permission.DATA_WRITE) is False

    def test_user_has_write_permissions(self):
        """测试普通用户有写权限"""
        assert check_permission(UserRole.USER, Permission.CONFIG_WRITE) is True
        assert check_permission(UserRole.USER, Permission.DATA_WRITE) is True

    def test_admin_has_all_permissions(self):
        """测试管理员有所有权限"""
        for perm in Permission:
            assert check_permission(UserRole.ADMIN, perm) is True

    def test_unknown_role_no_permissions(self):
        """测试未知角色无权限"""
        assert check_permission(None, Permission.CONFIG_READ) is False


class TestGetUserRoleFromToken:
    """测试 get_user_role_from_token 函数"""

    def test_valid_guest_token(self):
        """测试有效的访客令牌"""
        mock_token = "valid_guest_token"

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "guest"}
            role = get_user_role_from_token(mock_token)
            assert role == UserRole.GUEST

    def test_valid_user_token(self):
        """测试有效的用户令牌"""
        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "user"}
            role = get_user_role_from_token("valid_token")
            assert role == UserRole.USER

    def test_valid_admin_token(self):
        """测试有效的管理员令牌"""
        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "admin"}
            role = get_user_role_from_token("valid_token")
            assert role == UserRole.ADMIN

    def test_missing_role_defaults_to_guest(self):
        """测试缺少角色时默认为访客"""
        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {}
            role = get_user_role_from_token("valid_token")
            assert role == UserRole.GUEST

    def test_invalid_token_raises_401(self):
        """测试无效令牌抛出401异常"""
        from utils.jwt_utils import JWTError

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.side_effect = JWTError("Invalid token")
            with pytest.raises(HTTPException) as exc_info:
                get_user_role_from_token("invalid_token")
            assert exc_info.value.status_code == 401


class TestIsGuestUser:
    """测试 is_guest_user 函数

    语义约定：token 有效且 role=guest 时返回 True（调用方返回 403）；
    未携带 token / 格式错误 / token 无效或过期属于"未认证"，抛
    HTTPException(401) 让前端自动跳转登录页，而不是伪装成访客。
    """

    def test_no_auth_header_raises_401(self):
        """测试没有认证头抛 401"""
        request = Mock()
        request.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            is_guest_user(request)
        assert exc_info.value.status_code == 401

    def test_empty_auth_header_raises_401(self):
        """测试空认证头抛 401"""
        request = Mock()
        request.headers = {"Authorization": ""}
        with pytest.raises(HTTPException) as exc_info:
            is_guest_user(request)
        assert exc_info.value.status_code == 401

    def test_guest_token(self):
        """测试访客令牌"""
        request = Mock()
        request.headers = {"Authorization": "Bearer guest_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "guest"}
            assert is_guest_user(request) is True

    def test_user_token(self):
        """测试用户令牌"""
        request = Mock()
        request.headers = {"Authorization": "Bearer user_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "user"}
            assert is_guest_user(request) is False

    def test_invalid_token_raises_401(self):
        """测试无效令牌抛 401（不再伪装成访客）"""
        from utils.jwt_utils import JWTError

        request = Mock()
        request.headers = {"Authorization": "Bearer invalid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.side_effect = JWTError("Invalid")
            with pytest.raises(HTTPException) as exc_info:
                is_guest_user(request)
            assert exc_info.value.status_code == 401

    def test_expired_token_raises_401_with_expiry_message(self):
        """测试过期令牌抛 401 且提示登录过期"""
        from utils.jwt_utils import TokenExpiredError

        request = Mock()
        request.headers = {"Authorization": "Bearer expired_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.side_effect = TokenExpiredError()
            with pytest.raises(HTTPException) as exc_info:
                is_guest_user(request)
            assert exc_info.value.status_code == 401
            assert "过期" in str(exc_info.value.detail)

    def test_malformed_auth_header_raises_401(self):
        """测试格式错误的认证头抛 401"""
        request = Mock()
        request.headers = {"Authorization": "InvalidFormat"}
        with pytest.raises(HTTPException) as exc_info:
            is_guest_user(request)
        assert exc_info.value.status_code == 401

    def test_config_auth_disabled_returns_false(self):
        """config.toml 关闭校验（security.auth_enabled=false）时直接按非访客放行，不抛 401"""
        request = Mock()
        request.headers = {}
        with patch("utils.rbac.is_auth_check_disabled", return_value=True):
            assert is_guest_user(request) is False


class TestGetCurrentUserId:
    """测试 get_current_user_id 函数"""

    def test_no_auth_header(self):
        """测试没有认证头"""
        request = Mock()
        request.headers = {}
        assert get_current_user_id(request) is None

    def test_valid_user_id(self):
        """测试有效用户ID"""
        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"sub": "12345"}
            user_id = get_current_user_id(request)
            assert user_id == 12345

    def test_string_user_id_conversion(self):
        """测试字符串用户ID转换"""
        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"sub": "67890"}
            user_id = get_current_user_id(request)
            assert user_id == 67890

    def test_missing_sub(self):
        """测试缺少sub字段"""
        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {}
            assert get_current_user_id(request) is None

    def test_non_numeric_sub(self):
        """测试非数字sub"""
        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"sub": "guest_abc123"}
            assert get_current_user_id(request) is None

    def test_invalid_token(self):
        """测试无效令牌"""
        from utils.jwt_utils import JWTError

        request = Mock()
        request.headers = {"Authorization": "Bearer invalid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.side_effect = JWTError("Invalid")
            assert get_current_user_id(request) is None


class TestRequirePermissionSync:
    """测试 require_permission_sync 装饰器"""

    def test_permission_granted(self):
        """测试权限被授予"""

        @require_permission_sync(Permission.CONFIG_READ)
        def protected_func(request):
            return {"success": True}

        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "user"}
            result = protected_func(request)
            assert result == {"success": True}

    def test_permission_denied_raises_403(self):
        """测试权限被拒绝抛出403"""

        @require_permission_sync(Permission.CONFIG_WRITE)
        def protected_func(request):
            return {"success": True}

        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "guest"}
            with pytest.raises(HTTPException) as exc_info:
                protected_func(request)
            assert exc_info.value.status_code == 403
            assert "权限不足" in exc_info.value.detail["message"]

    def test_no_token_raises_401(self):
        """测试没有令牌抛出401"""

        @require_permission_sync(Permission.CONFIG_READ)
        def protected_func(request):
            return {"success": True}

        request = Mock()
        request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            protected_func(request)
        assert exc_info.value.status_code == 401

    def test_invalid_token_format_raises_401(self):
        """测试无效令牌格式抛出401"""

        @require_permission_sync(Permission.CONFIG_READ)
        def protected_func(request):
            return {"success": True}

        request = Mock()
        request.headers = {"Authorization": "Bearer"}

        with pytest.raises(HTTPException) as exc_info:
            protected_func(request)
        assert exc_info.value.status_code == 401


class TestGetCurrentUserInfo:
    """测试 get_current_user_info 函数"""

    def test_no_auth_header_returns_guest(self):
        """测试没有认证头返回访客信息"""
        request = Mock()
        request.headers = {}
        info = get_current_user_info(request)
        assert info["role"] == "guest"
        assert info["is_guest"] is True

    def test_valid_user_token(self):
        """测试有效用户令牌"""
        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {
                "sub": "user123",
                "name": "Test User",
                "role": "user",
            }
            info = get_current_user_info(request)
            assert info["sub"] == "user123"
            assert info["name"] == "Test User"
            assert info["role"] == "user"
            assert info["is_guest"] is False

    def test_guest_token(self):
        """测试访客令牌"""
        request = Mock()
        request.headers = {"Authorization": "Bearer guest_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "guest"}
            info = get_current_user_info(request)
            assert info["role"] == "guest"
            assert info["is_guest"] is True

    def test_invalid_token_returns_guest(self):
        """测试无效令牌返回访客信息"""
        from utils.jwt_utils import JWTError

        request = Mock()
        request.headers = {"Authorization": "Bearer invalid_token"}

        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.side_effect = JWTError("Invalid")
            info = get_current_user_info(request)
            assert info["role"] == "guest"
            assert info["is_guest"] is True


class TestRoleHierarchy:
    """测试角色层次结构"""

    def test_admin_has_all_permissions(self):
        """测试管理员拥有所有定义的权限"""
        admin_perms = ROLE_PERMISSIONS[UserRole.ADMIN]
        guest_perms = ROLE_PERMISSIONS[UserRole.GUEST]
        user_perms = ROLE_PERMISSIONS[UserRole.USER]
        assert admin_perms >= user_perms
        assert admin_perms >= guest_perms

    def test_guest_has_subset_of_permissions(self):
        """测试访客权限是用户权限的子集"""
        guest_perms = ROLE_PERMISSIONS[UserRole.GUEST]
        user_perms = ROLE_PERMISSIONS[UserRole.USER]
        assert guest_perms <= user_perms


class TestEdgeCases:
    """测试边界情况"""

    def test_case_sensitive_role(self):
        """测试角色名大小写敏感"""
        with patch("utils.rbac.decode_jwt_token") as mock_decode:
            mock_decode.return_value = {"role": "USER"}
            with pytest.raises(ValueError):
                UserRole(mock_decode.return_value["role"])

    def test_permission_string_format(self):
        """测试权限字符串格式"""
        for perm in Permission:
            parts = perm.value.split(":")
            assert len(parts) == 2
            assert parts[0] in [
                "config",
                "user",
                "strategy",
                "indicator",
                "backtest",
                "data",
                "ai",
                "log",
                "exchange",
                "worker",
            ]
            assert parts[1] in ["read", "write", "operate"]


class TestWorkerPermissions:
    """P1-07 worker 权限枚举落地：read/write/operate 与角色映射"""

    def test_permission_values(self):
        assert Permission.WORKER_READ.value == "worker:read"
        assert Permission.WORKER_WRITE.value == "worker:write"
        assert Permission.WORKER_OPERATE.value == "worker:operate"

    def test_guest_read_only(self):
        """访客可读 worker 但不可写/操作"""
        guest_perms = ROLE_PERMISSIONS[UserRole.GUEST]
        assert Permission.WORKER_READ in guest_perms
        assert Permission.WORKER_WRITE not in guest_perms
        assert Permission.WORKER_OPERATE not in guest_perms

    def test_user_full_worker_access(self):
        user_perms = ROLE_PERMISSIONS[UserRole.USER]
        assert Permission.WORKER_READ in user_perms
        assert Permission.WORKER_WRITE in user_perms
        assert Permission.WORKER_OPERATE in user_perms


class _FakeRequest:
    """require_permission 依赖的最小请求替身（headers + url.path）"""

    def __init__(self, headers=None, path="/api/v1/workers"):
        self.headers = headers or {}
        self.url = Mock()
        self.url.path = path


class TestRequirePermissionDep:
    """测试 require_permission FastAPI 依赖（P1-07 灰度挂载点）

    开关 rbac.enforcement_enabled（config 默认 false）：
    - off：旁路放行，行为与未挂载一致（现有测试链路零影响）
    - on：无 token/无效 token 401（未认证语义，与 is_guest_user 一致）、
      权限不足 403、通过放行；拒绝与通过均写审计日志
    """

    def _dep(self, permission=Permission.WORKER_WRITE):
        # require_permission(p) 直接返回 async 依赖函数（路由里包在 Depends 中）
        return require_permission(permission)

    def _run(self, dep, request):
        asyncio.run(dep(request))

    def test_enforcement_off_bypasses_even_without_token(self):
        """off 时无 token 也放行（现行为，回归保护）"""
        with patch("utils.config_manager.get_value", return_value=False):
            self._run(self._dep(), _FakeRequest(headers={}))

    def test_enforcement_on_no_token_401(self):
        with patch("utils.config_manager.get_value", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                self._run(self._dep(), _FakeRequest(headers={}))
        assert exc_info.value.status_code == 401

    def test_enforcement_on_malformed_header_401(self):
        with patch("utils.config_manager.get_value", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                self._run(self._dep(), _FakeRequest(headers={"Authorization": "InvalidFormat"}))
        assert exc_info.value.status_code == 401

    def test_enforcement_on_invalid_token_401(self):
        from utils.jwt_utils import JWTError

        with (
            patch("utils.config_manager.get_value", return_value=True),
            patch("utils.rbac.decode_jwt_token", side_effect=JWTError("bad")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                self._run(self._dep(), _FakeRequest(headers={"Authorization": "Bearer bad"}))
        assert exc_info.value.status_code == 401

    def test_enforcement_on_expired_token_401(self):
        from utils.jwt_utils import TokenExpiredError

        with (
            patch("utils.config_manager.get_value", return_value=True),
            patch("utils.rbac.decode_jwt_token", side_effect=TokenExpiredError()),
        ):
            with pytest.raises(HTTPException) as exc_info:
                self._run(self._dep(), _FakeRequest(headers={"Authorization": "Bearer expired"}))
        assert exc_info.value.status_code == 401
        assert "过期" in str(exc_info.value.detail)

    def test_enforcement_on_guest_write_403(self):
        with (
            patch("utils.config_manager.get_value", return_value=True),
            patch("utils.rbac.decode_jwt_token", return_value={"sub": "1", "role": "guest"}),
        ):
            with pytest.raises(HTTPException) as exc_info:
                self._run(self._dep(), _FakeRequest(headers={"Authorization": "Bearer 1"}, path="/api/v1/workers"))
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["data"]["required_permission"] == "worker:write"

    def test_enforcement_on_guest_read_allowed(self):
        with (
            patch("utils.config_manager.get_value", return_value=True),
            patch("utils.rbac.decode_jwt_token", return_value={"sub": "1", "role": "guest"}),
        ):
            self._run(
                self._dep(Permission.WORKER_READ),
                _FakeRequest(headers={"Authorization": "Bearer 1"}, path="/api/v1/workers"),
            )

    def test_enforcement_on_user_operate_allowed(self):
        with (
            patch("utils.config_manager.get_value", return_value=True),
            patch("utils.rbac.decode_jwt_token", return_value={"sub": "2", "role": "user"}),
        ):
            self._run(
                self._dep(Permission.WORKER_OPERATE),
                _FakeRequest(headers={"Authorization": "Bearer 1"}, path="/api/v1/workers/1/start"),
            )

    def test_denial_writes_audit_log(self):
        """403 拒绝时写审计日志（user/permission/result）"""
        with (
            patch("utils.config_manager.get_value", return_value=True),
            patch("utils.rbac.decode_jwt_token", return_value={"sub": "1", "role": "guest"}),
            patch("utils.rbac.logger") as mock_logger,
        ):
            with pytest.raises(HTTPException):
                self._run(
                    self._dep(),
                    _FakeRequest(headers={"Authorization": "Bearer 1"}, path="/api/v1/workers"),
                )
        denied_call = "".join(str(c) for c in mock_logger.warning.call_args_list)
        assert "denied" in denied_call and "worker:write" in denied_call


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
