import os
from pathlib import Path
from config_manager import get_config

# 获取支持的语言列表
SUPPORTED_LOCALES = ["zh-CN", "en-US"]

# 设置gettext相关环境变量
def setup_gettext():
    # 获取统一的国际化目录路径
    unified_i18n_dir = Path("/Users/liupeng/workspace/quantcell/i18n")
    
    # 设置环境变量 - fastapi_i18n使用gettext，需要正确的目录结构
    # gettext期望的目录结构是：locale_dir/locale/LC_MESSAGES/messages.mo
    # 但我们使用的是JSON文件，所以需要转换或修改配置
    os.environ["FASTAPI_I18N__LOCALE_DIR"] = str(unified_i18n_dir)
    os.environ["FASTAPI_I18N__LOCALE_DEFAULT"] = get_config("language", "zh-CN")
    
    return unified_i18n_dir

# 从数据库获取当前语言配置，默认使用中文
def get_current_locale():
    return get_config("language", "zh-CN")

# 初始化gettext配置
locales_dir = setup_gettext()