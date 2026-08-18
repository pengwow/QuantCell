import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

from utils.logger import LogType, get_logger

from .plugin_security import validate_permissions
from .plugin_store import PluginStore

logger = get_logger(__name__, LogType.APPLICATION)

MANIFEST_NAME = "manifest.json"
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class PluginInstaller:
    def __init__(self, plugin_dir: str, plugin_manager=None):
        self.plugin_dir = plugin_dir
        self.plugin_manager = plugin_manager

    def install_from_zip(self, zip_file_path: str) -> tuple[bool, str]:
        if not os.path.isfile(zip_file_path):
            return False, f"ZIP 文件不存在: {zip_file_path}"

        temp_dir = tempfile.mkdtemp(prefix="plugin_install_")
        try:
            with zipfile.ZipFile(zip_file_path, "r") as zf:
                zf.extractall(temp_dir)

            manifest_path, manifest_data = self._find_manifest(temp_dir)
            if manifest_path is None:
                return False, "ZIP 中未找到 manifest.json"

            valid, msg = self.validate_manifest(manifest_data)
            if not valid:
                return False, msg

            plugin_name = manifest_data["name"]
            existing = PluginStore.get_plugin(plugin_name)
            if existing:
                return False, f"插件 {plugin_name} 已存在，请先卸载后再安装"

            source_dir = os.path.dirname(manifest_path)
            dest_dir = os.path.join(self.plugin_dir, plugin_name)
            if os.path.exists(dest_dir):
                shutil.rmtree(dest_dir)
            shutil.move(source_dir, dest_dir)

            if self.plugin_manager is not None:
                install_path = dest_dir
                success = self.plugin_manager.install_plugin(install_path, manifest_data, source_type="zip")
                if not success:
                    if os.path.exists(dest_dir):
                        shutil.rmtree(dest_dir)
                    return False, f"插件 {plugin_name} 安装失败（PluginManager 拒绝）"

            logger.info(f"插件 {plugin_name} 从 ZIP 安装成功")
            return True, f"插件 {plugin_name} 安装成功"

        except zipfile.BadZipFile:
            return False, "无效的 ZIP 文件"
        except Exception as e:
            logger.error(f"从 ZIP 安装插件失败: {e}", exception=e)
            return False, f"安装失败: {e}"
        finally:
            self._cleanup_temp(temp_dir)

    def install_from_zip_bytes(self, zip_bytes: bytes, filename: str = "plugin.zip") -> tuple[bool, str]:
        temp_dir = tempfile.mkdtemp(prefix="plugin_install_")
        temp_zip_path = os.path.join(temp_dir, filename)
        try:
            with open(temp_zip_path, "wb") as f:
                f.write(zip_bytes)
            return self.install_from_zip(temp_zip_path)
        except Exception as e:
            logger.error(f"从字节数据安装插件失败: {e}", exception=e)
            return False, f"安装失败: {e}"
        finally:
            self._cleanup_temp(temp_dir)

    def install_from_git(self, git_url: str, branch: str | None = None) -> tuple[bool, str]:
        temp_dir = tempfile.mkdtemp(prefix="plugin_git_")
        clone_dir = os.path.join(temp_dir, "repo")
        try:
            cmd = ["git", "clone", "--depth", "1"]
            if branch:
                cmd.extend(["--branch", branch])
            cmd.extend([git_url, clone_dir])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return False, f"git clone 失败: {result.stderr.strip()}"

            manifest_path, manifest_data = self._find_manifest(clone_dir)
            if manifest_path is None:
                return False, "仓库中未找到 manifest.json"

            valid, msg = self.validate_manifest(manifest_data)
            if not valid:
                return False, msg

            plugin_name = manifest_data["name"]
            existing = PluginStore.get_plugin(plugin_name)
            if existing:
                return False, f"插件 {plugin_name} 已存在，请先卸载后再安装"

            source_dir = os.path.dirname(manifest_path)
            dest_dir = os.path.join(self.plugin_dir, plugin_name)
            if os.path.exists(dest_dir):
                shutil.rmtree(dest_dir)
            shutil.move(source_dir, dest_dir)

            if self.plugin_manager is not None:
                success = self.plugin_manager.install_plugin(dest_dir, manifest_data, source_type="git")
                if not success:
                    if os.path.exists(dest_dir):
                        shutil.rmtree(dest_dir)
                    return False, f"插件 {plugin_name} 安装失败（PluginManager 拒绝）"

            logger.info(f"插件 {plugin_name} 从 Git 安装成功")
            return True, f"插件 {plugin_name} 安装成功"

        except subprocess.TimeoutExpired:
            return False, "git clone 超时（120秒）"
        except Exception as e:
            logger.error(f"从 Git 安装插件失败: {e}", exception=e)
            return False, f"安装失败: {e}"
        finally:
            self._cleanup_temp(temp_dir)

    def validate_manifest(self, manifest_data: dict) -> tuple[bool, str]:
        name = manifest_data.get("name")
        if not name:
            return False, "manifest 缺少 name 字段"
        if not NAME_PATTERN.match(name):
            return (
                False,
                f"插件名称格式不合法: {name}，仅允许字母、数字、下划线、连字符",
            )

        version = manifest_data.get("version")
        if not version:
            return False, "manifest 缺少 version 字段"
        if not VERSION_PATTERN.match(version):
            return False, f"版本号格式不合法: {version}，需符合 X.Y.Z 格式"

        permissions = manifest_data.get("permissions", [])
        if permissions:
            perm_valid, perm_msg = validate_permissions(permissions)
            if not perm_valid:
                return False, f"权限校验失败: {perm_msg}"

        return True, ""

    def _find_manifest(self, root_dir: str) -> tuple[str | None, dict | None]:
        direct_path = os.path.join(root_dir, MANIFEST_NAME)
        if os.path.isfile(direct_path):
            try:
                with open(direct_path, encoding="utf-8") as f:
                    return direct_path, json.load(f)
            except json.JSONDecodeError, OSError:
                return None, None

        for entry in os.listdir(root_dir):
            sub_path = os.path.join(root_dir, entry, MANIFEST_NAME)
            if os.path.isfile(sub_path):
                try:
                    with open(sub_path, encoding="utf-8") as f:
                        return sub_path, json.load(f)
                except json.JSONDecodeError, OSError:
                    return None, None

        return None, None

    def _cleanup_temp(self, temp_dir: str):
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"清理临时目录失败: {temp_dir}, {e}")
