"""设置项 Schema 定义（P2-05 设置 schema 化）。

设计目标：新增一个用户可配置项，只需在本文件的 SETTINGS_SCHEMA 声明一处，
即可由 GET /api/v1/config/schema 暴露给前端，由 GET /api/v1/config/values
读取现值、PUT /api/v1/config/values 写入——前端 schema 渲染器按分组自动
渲染表单，无需再改前端页面代码。

存储口径：所有字段落在 SystemConfig 表（key-value 字符串），存储规则与
SystemConfigBusiness.set 一致——bool 存 "1"/"0"，其余 str(value)。
分组 key 同时作为存储记录的 name，与前端旧接口 getConfig 按 name 分组的
口径保持一致（如 general 组字段 name='general'）。

与能力开关（config/capabilities.py）的边界：capabilities 的取值链是
env > config.toml [capabilities] > 内置默认值，属于只读部署配置，不走
SystemConfig 存储；若挂进本 schema 的 values 写通道会与 env 覆盖优先级
产生双源冲突。M4.2 如需打通，应在 SchemaGroup 增加 source 声明，让
values 端点对只读组拒绝写入，而不是把 capabilities 搬进 SystemConfig。

label 存前端 i18n key；description 为落库到 system_config.description 的
说明文本，倾向直接写中文（设置页/配置管理页直接展示，i18n 收益低）。
特殊控件（如主题图片选择器）属于渲染器逃生口的范畴，见前端渲染器的
CUSTOM_WIDGETS 注册表，本 schema 不承载 UI 细节。
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from settings.models import SystemConfigBusiness


class FieldType(StrEnum):
    """字段类型，渲染器按此映射 antd 控件：

    bool -> Switch / number -> InputNumber / select -> Select /
    string -> Input / text -> TextArea
    """

    BOOL = "bool"
    NUMBER = "number"
    STRING = "string"
    SELECT = "select"
    TEXT = "text"


class SchemaOption(BaseModel):
    """select 字段的候选项；value 为存储值，label 为前端 i18n key 或可读文本"""

    value: str | int
    label: str


class SchemaField(BaseModel):
    """单个设置项定义"""

    key: str = Field(..., description="配置键名，即 SystemConfig.key")
    label: str = Field(..., description="显示名（前端 i18n key）")
    type: FieldType = Field(..., description="字段类型，渲染器据此映射控件")
    default: Any = Field(..., description="未存储时的默认值（Python 原生类型）")
    description: str | None = Field(None, description="字段说明（前端 i18n key 或文本）")
    options: list[SchemaOption] = Field(
        default_factory=list,
        description="select / 带档位 number 字段的候选值",
    )
    advanced: bool = Field(
        default=False,
        description="高级字段：前端渲染器默认折叠在「高级设置」Collapse 内",
    )


class SchemaGroup(BaseModel):
    """设置分组，key 同时作为 SystemConfig.name 的分组标识"""

    key: str = Field(..., description="分组标识，如 general")
    title: str = Field(..., description="分组标题（前端 i18n key）")
    description: str | None = Field(None, description="分组说明")
    order: int = Field(default=0, description="渲染顺序，小者在前")
    fields: list[SchemaField] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema 登记处：新增配置项只改这里
# ---------------------------------------------------------------------------

_SETTING_TIMEZONES = [
    ("Asia/Shanghai", "timezone_shanghai"),
    ("Asia/Hong_Kong", "timezone_hongkong"),
    ("Asia/Tokyo", "timezone_tokyo"),
    ("Asia/Singapore", "timezone_singapore"),
    ("America/New_York", "timezone_newyork"),
    ("America/Los_Angeles", "timezone_losangeles"),
    ("Europe/London", "timezone_london"),
    ("Europe/Paris", "timezone_paris"),
    ("Australia/Sydney", "timezone_sydney"),
    ("UTC", "timezone_utc"),
]

SETTINGS_SCHEMA: dict[str, SchemaGroup] = {
    "general": SchemaGroup(
        key="general",
        title="general_settings",
        order=0,
        fields=[
            SchemaField(
                key="theme",
                label="theme",
                type=FieldType.SELECT,
                default="light",
                description="界面主题：light 亮色 / dark 暗色 / auto 跟随系统",
                options=[
                    SchemaOption(value="light", label="theme_light"),
                    SchemaOption(value="dark", label="theme_dark"),
                    SchemaOption(value="auto", label="theme_auto"),
                ],
            ),
            SchemaField(
                key="language",
                label="language",
                type=FieldType.SELECT,
                default="zh-CN",
                description="界面显示语言",
                options=[
                    SchemaOption(value="zh-CN", label="language_zh_cn"),
                    SchemaOption(value="en-US", label="English"),
                ],
            ),
            SchemaField(
                key="defaultPerPage",
                label="default_per_page",
                type=FieldType.NUMBER,
                # 档位与前端 constants/pagination 的 PER_PAGE_OPTIONS 保持 12 倍数口径
                default=12,
                description="列表默认每页条数",
                options=[SchemaOption(value=n, label=str(n)) for n in (12, 24, 36, 48, 96)],
            ),
            SchemaField(
                key="defaultViewType",
                label="settings_view_type_label",
                type=FieldType.SELECT,
                default="card",
                description="settings_view_type_hint",
                options=[
                    SchemaOption(value="card", label="settings_view_type_card"),
                    SchemaOption(value="list", label="settings_view_type_list"),
                ],
            ),
            SchemaField(
                key="showTips",
                label="show_tips",
                type=FieldType.BOOL,
                default=True,
                description="是否显示新手引导提示",
                advanced=True,
            ),
            SchemaField(
                key="timezone",
                label="default_timezone",
                type=FieldType.SELECT,
                default="Asia/Shanghai",
                description="全局默认时区（各页面时区切换的初始值）",
                options=[SchemaOption(value=v, label=lab) for v, lab in _SETTING_TIMEZONES],
            ),
        ],
    ),
    # 图表页用户偏好：值是 JSON 字符串（前端解析），进 schema 是为了复用
    # values 读写通道与类型校验；chart.indicatorParams.* 动态键不走 schema（品种无法预声明）
    "chart": SchemaGroup(
        key="chart",
        title="chart_settings",
        order=1,
        fields=[
            SchemaField(
                key="priceStyle",
                label="chart_price_style",
                type=FieldType.STRING,
                default="{}",
                description="图表样式设置，JSON 字符串（klinecharts 样式 path -> value）",
            ),
            SchemaField(
                key="uiPrefs",
                label="chart_ui_prefs",
                type=FieldType.STRING,
                default="{}",
                description="图表页偏好，JSON 字符串（period/symbol/timezone）",
            ),
        ],
    ),
}


# ---------------------------------------------------------------------------
# 类型还原与序列化：values 端点的读写转换
# ---------------------------------------------------------------------------

# 与 GeneralSettings 前端口径一致：合法枚举外的 theme 值视为未配置，回退默认
_TRUTHY_STRINGS = {"1", "true", "True"}


def restore_value(field: SchemaField, stored: str | None) -> Any:
    """SystemConfig 存储字符串 -> schema 类型还原；未存储时返回 default。

    类型不合法的存量值回退 default（QtCell 存储层无类型约束，脏数据兜底），
    不抛异常——读取路径要稳，坏一个字段不能拖垮整个 values 响应。
    """
    if stored is None:
        return field.default
    try:
        if field.type == FieldType.BOOL:
            return stored in _TRUTHY_STRINGS
        if field.type == FieldType.NUMBER:
            num = float(stored)
            return int(num) if num.is_integer() else num
        return stored
    except ValueError, TypeError:
        return field.default


def store_value(field: SchemaField, value: Any) -> str:
    """请求值 -> SystemConfig 存储字符串（bool 与 SystemConfigBusiness.set 口径一致）。

    校验失败抛 ValueError，由路由层转 400。
    """
    if field.type == FieldType.BOOL:
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, str) and value in _TRUTHY_STRINGS | {"0", "false", "False"}:
            return "1" if value in _TRUTHY_STRINGS else "0"
        raise ValueError(f"字段 {field.key} 需要 bool 值")
    if field.type == FieldType.NUMBER:
        try:
            num = float(value)
        except ValueError, TypeError:
            raise ValueError(f"字段 {field.key} 需要数字值") from None
        # 整值去掉 ".0" 尾巴，与旧配置入口存 "24" 的口径完全一致
        return str(int(num)) if num.is_integer() else str(num)
    if field.type == FieldType.SELECT:
        text = str(value)
        if field.options and all(opt.value != value for opt in field.options):
            allowed = [str(opt.value) for opt in field.options]
            raise ValueError(f"字段 {field.key} 的合法取值为 {allowed}")
        return text
    return str(value)


def serialize_schema() -> dict[str, Any]:
    """settings 端点响应体：按 order 排序的分组列表"""
    groups = sorted(SETTINGS_SCHEMA.values(), key=lambda g: g.order)
    return {"groups": [group.model_dump() for group in groups]}


def iter_fields():
    """遍历所有 (group, field)，供 values 读写定位归属分组"""
    for group in sorted(SETTINGS_SCHEMA.values(), key=lambda g: g.order):
        for field in group.fields:
            yield group, field


def find_field(key: str) -> tuple[SchemaGroup, SchemaField] | None:
    """按配置键查找归属分组与字段定义；未在 schema 声明的 key 返回 None"""
    for group, field in iter_fields():
        if field.key == key:
            return group, field
    return None


def read_setting_values() -> dict[str, Any]:
    """GET /values 响应体：全量 schema 字段 -> 现值（default 兜底，类型已还原）"""
    stored = SystemConfigBusiness.get_all()
    return {field.key: restore_value(field, stored.get(field.key)) for _, field in iter_fields()}


def write_setting_values(values: dict[str, Any]) -> int:
    """PUT /values：按 schema 校验并批量写入 SystemConfig，返回写入数。

    两阶段执行——先全量校验（未知 key / 类型不符 / select 越界）再统一落库，
    避免"写一半"的部分成功状态；任一校验失败抛 ValueError，由路由层转 400。
    """
    errors: list[str] = []
    prepared: list[tuple[str, str, str]] = []  # (key, str_value, group.name)
    for key, value in values.items():
        hit = find_field(key)
        if hit is None:
            errors.append(f"未知配置项: {key}")
            continue
        group, field = hit
        try:
            prepared.append((key, store_value(field, value), group.key))
        except ValueError as e:
            errors.append(str(e))
    if errors:
        raise ValueError("; ".join(errors))

    written = 0
    for key, str_value, group_name in prepared:
        field = find_field(key)[1]
        if SystemConfigBusiness.set(
            key=key,
            value=str_value,
            # 描述随 schema 落库；set 对已存在行仅非空才覆盖，不会冲掉人工描述
            description=field.description or "",
            name=group_name,
        ):
            written += 1
    return written


def backfill_descriptions() -> int:
    """启动幂等回填：存量行 description 为空的 schema 声明键，按 schema 补描述。

    只补空、不覆盖已有人工描述，也不为不存在的 key 造行（避免凭空写入
    尚未使用过的配置项）。返回回填行数，供启动日志观测。
    """
    count = 0
    for _, field in iter_fields():
        if field.description and SystemConfigBusiness.update_description_if_empty(field.key, field.description):
            count += 1
    return count
