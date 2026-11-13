/**
 * 图表页用户偏好持久化（设计见 docs/superpowers/specs/2026-11-13-chart-settings-persistence-design.md）。
 *
 * 存储：后端 system_config 的 chart 组，GET /api/v1/config/ 按 name 分组一次拉回：
 * - priceStyle：设置弹窗 7 项（SETTINGS_SCHEMA 静态声明，JSON 字符串）
 * - uiPrefs：品种/周期/时区（静态声明，JSON 字符串）
 * - indicatorParams.{symbolCode}.{indicatorId}：指标参数（品种×指标二维动态键）
 *
 * 错误策略（设计约定）：读失败静默走默认；写失败仅 console.warn，会话内仍生效，不打断交易体验。
 */
import { configApi } from '../api';

export interface ChartUiPrefs {
  period?: string;
  symbol?: string;
  timezone?: string;
}

export interface ChartPrefsSnapshot {
  /** 设置弹窗 7 项：klinecharts 样式 path -> value */
  priceStyle: Record<string, unknown>;
  uiPrefs: ChartUiPrefs;
  /** "symbolCode.indicatorId" -> 参数对象 */
  indicatorParams: Record<string, Record<string, unknown>>;
}

const CHART_GROUP = 'chart';
const PARAMS_PREFIX = 'indicatorParams.';
const UI_PREFS_KEY = 'uiPrefs';
const DEBOUNCE_MS = 800;
// indicatorParams 动态键落库时的描述（schema 不覆盖动态键，只能写入方携带）
const INDICATOR_PARAMS_DESCRIPTION = '图表指标参数（品种×指标维度），由图表页自动保存，JSON 对象';

// 旧 localStorage 键（持久化切后端前的一次性迁移来源；迁移成功后清理）
const LEGACY_USER_PREFS_KEY = 'chart_user_preferences';
const legacyIndicatorParamsKey = (symbolCode: string, indicatorId: string) =>
  `qc:indicator-params:${symbolCode}:${indicatorId}`;

// ---- 模块级状态：load 后的服务端快照 + 防抖 buffer ----
// ponytail: 单实例缓存——图表页只有一份偏好，跨标签页不同步，刷新即拉新值；
// 若未来需要跨标签页实时同步，升级路径是 BroadcastChannel 广播 setter
let priceStyleServer: Record<string, unknown> = {};
let priceStyleBuffer: Record<string, unknown> = {};
let uiPrefsServer: ChartUiPrefs = {};
let uiPrefsBuffer: Partial<ChartUiPrefs> = {};
let indicatorParamsSnapshot: Record<string, Record<string, unknown>> = {};
let loaded = false;
let loadPromise: Promise<ChartPrefsSnapshot> | null = null;
let priceStyleTimer: ReturnType<typeof setTimeout> | null = null;
let uiPrefsTimer: ReturnType<typeof setTimeout> | null = null;

const parsePref = (raw: unknown): Record<string, unknown> => {
  if (typeof raw !== 'string' || !raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
};

// GET /config/{key} 对不存在的键返回 code=1，会被 apiRequest 拦截器 reject 并打
// console.error 噪声——所以一律走全量 getConfig()（按 name 分组自带 chart 组），
// 不做单键 GET；持久化写入也统一 name='chart'，保证旧接口分组口径一致
const migrateLegacyUserPrefs = (chartGroup: Record<string, unknown>): ChartUiPrefs => {
  if (chartGroup[UI_PREFS_KEY] !== undefined) {
    return parsePref(chartGroup[UI_PREFS_KEY]) as ChartUiPrefs;
  }
  let legacy: ChartUiPrefs = {};
  try {
    const raw = localStorage.getItem(LEGACY_USER_PREFS_KEY);
    if (raw) legacy = parsePref(raw) as ChartUiPrefs;
  } catch {
    // localStorage 不可用（隐私模式等）时跳过迁移
  }
  if (Object.keys(legacy).length > 0) {
    // 迁移失败静默：下次 load 仍会重试（旧键已清，兜底链是后端 -> 本次会话默认值）
    configApi
      .setConfigKey({ key: UI_PREFS_KEY, value: JSON.stringify(legacy), name: CHART_GROUP })
      .catch(() => undefined);
  }
  try {
    localStorage.removeItem(LEGACY_USER_PREFS_KEY);
  } catch {
    // 忽略
  }
  return legacy;
};

const migrateLegacyIndicatorParams = (
  symbolCode: string,
  indicatorId: string,
): void => {
  // 后端动态键带 "indicatorParams." 前缀，快照内部的键是 "symbolCode.indicatorId"，读写时各自拼
  const snapshotKey = `${symbolCode}.${indicatorId}`;
  const backendKey = `${PARAMS_PREFIX}${snapshotKey}`;
  if (indicatorParamsSnapshot[snapshotKey] !== undefined) return;
  try {
    const raw = localStorage.getItem(legacyIndicatorParamsKey(symbolCode, indicatorId));
    if (!raw) return;
    const params = parsePref(raw);
    if (Object.keys(params).length === 0) return;
    indicatorParamsSnapshot[snapshotKey] = params;
    configApi
      .setConfigKey({
        key: backendKey,
        value: JSON.stringify(params),
        name: CHART_GROUP,
        // 动态键没有 schema 描述兜底，描述由写入方携带（一次性设置，更新时后端仅非空才覆盖）
        description: INDICATOR_PARAMS_DESCRIPTION,
      })
      .catch(() => undefined); // 迁移失败下次未命中仍会重试
    localStorage.removeItem(legacyIndicatorParamsKey(symbolCode, indicatorId));
  } catch {
    // 迁移失败走默认参数，不阻塞指标启动
  }
};

const finishLoad = (chartGroup: Record<string, unknown>): ChartPrefsSnapshot => {
  priceStyleServer = parsePref(chartGroup.priceStyle);
  uiPrefsServer = migrateLegacyUserPrefs(chartGroup);
  indicatorParamsSnapshot = {};
  for (const [rawKey, rawValue] of Object.entries(chartGroup)) {
    if (!rawKey.startsWith(PARAMS_PREFIX)) continue;
    const parsed = parsePref(rawValue);
    if (Object.keys(parsed).length > 0) {
      // 快照对外的键是 "symbolCode.indicatorId"（见 ChartPrefsSnapshot 注释），
      // 后端动态键的 "indicatorParams." 前缀只属于接口层，写回时再拼回
      indicatorParamsSnapshot[rawKey.slice(PARAMS_PREFIX.length)] = parsed;
    }
  }
  // 注意：这里不能清 priceStyleBuffer/uiPrefsBuffer —— mount 与 load 完成之间
  // 已缓冲的用户改动要等 loaded 后由 flush 写出，load 直接清会静默丢改动
  loaded = true;
  return {
    priceStyle: { ...priceStyleServer },
    uiPrefs: { ...uiPrefsServer },
    indicatorParams: indicatorParamsSnapshot,
  };
};

const doLoad = async (): Promise<ChartPrefsSnapshot> => {
  let grouped: Record<string, Record<string, unknown>> = {};
  try {
    grouped = (await configApi.getConfig()) as typeof grouped;
  } catch {
    grouped = {}; // 后端不可达：空快照走默认值 + localStorage 旧键兜底
  }
  return finishLoad(grouped[CHART_GROUP] ?? {});
};

/** 图表页挂载时调用一次；幂等（重复调用复用同一 Promise） */
export const loadChartPrefs = (): Promise<ChartPrefsSnapshot> => {
  if (!loadPromise) {
    loadPromise = doLoad().catch((error: unknown) => {
      console.warn('[chartPreferences] 读取图表偏好失败，走默认值', error);
      return finishLoad({});
    });
  }
  return loadPromise;
};

/** 清空 pending 防抖（恢复默认前调用，防晚到合并写复活已删配置） */
export const cancelPendingSaves = (): void => {
  if (priceStyleTimer) { clearTimeout(priceStyleTimer); priceStyleTimer = null; }
  if (uiPrefsTimer) { clearTimeout(uiPrefsTimer); uiPrefsTimer = null; }
  priceStyleBuffer = {};
  uiPrefsBuffer = {};
};

const flushPriceStyle = async (): Promise<void> => {
  priceStyleTimer = null;
  if (Object.keys(priceStyleBuffer).length === 0) return;
  // 未完成首次 load 不写：防 mount 瞬间默认值覆盖服务端配置；重新排队等活动完成
  if (!loaded) {
    priceStyleTimer = setTimeout(flushPriceStyle, DEBOUNCE_MS);
    return;
  }
  const merged = { ...priceStyleServer, ...priceStyleBuffer };
  try {
    await configApi.updateConfigValues({ priceStyle: JSON.stringify(merged) });
    priceStyleServer = merged;
    priceStyleBuffer = {};
  } catch (error) {
    console.warn('[chartPreferences] 保存图表样式失败', error);
  }
};

/** 设置弹窗单项变更：800ms 尾沿防抖合并写（恢复默认走 restorePriceStyle，不经过这里） */
export const savePriceStyleValue = (path: string, value: unknown): void => {
  priceStyleBuffer[path] = value;
  if (priceStyleTimer) clearTimeout(priceStyleTimer);
  priceStyleTimer = setTimeout(flushPriceStyle, DEBOUNCE_MS);
};

const flushUiPrefs = async (): Promise<void> => {
  uiPrefsTimer = null;
  if (Object.keys(uiPrefsBuffer).length === 0) return;
  if (!loaded) {
    uiPrefsTimer = setTimeout(flushUiPrefs, DEBOUNCE_MS);
    return;
  }
  const merged = { ...uiPrefsServer, ...uiPrefsBuffer };
  try {
    await configApi.updateConfigValues({ uiPrefs: JSON.stringify(merged) });
    uiPrefsServer = merged;
    uiPrefsBuffer = {};
  } catch (error) {
    console.warn('[chartPreferences] 保存图表偏好失败', error);
  }
};

/** 品种/周期/时区变更：800ms 防抖合并写 */
export const saveUiPrefs = (patch: Partial<ChartUiPrefs>): void => {
  uiPrefsBuffer = { ...uiPrefsBuffer, ...patch };
  if (uiPrefsTimer) clearTimeout(uiPrefsTimer);
  uiPrefsTimer = setTimeout(flushUiPrefs, DEBOUNCE_MS);
};

/**
 * 读取单条指标参数（同步读 load 快照；调用方需先 await loadChartPrefs()）。
 * 后端未命中时检查 localStorage 旧键并触发一次性迁移。
 */
export const loadIndicatorParams = (
  symbolCode: string,
  indicatorId: string,
): Record<string, unknown> | null => {
  const key = `${symbolCode}.${indicatorId}`;
  const hit = indicatorParamsSnapshot[key];
  if (hit) return hit;
  migrateLegacyIndicatorParams(symbolCode, indicatorId);
  return indicatorParamsSnapshot[key] ?? null;
};

/** 保存单条指标参数：低频操作，即时写动态键（无 schema 声明，走 POST /config/） */
export const saveIndicatorParams = async (
  symbolCode: string,
  indicatorId: string,
  params: Record<string, unknown>,
): Promise<void> => {
  const snapshotKey = `${symbolCode}.${indicatorId}`;
  const backendKey = `${PARAMS_PREFIX}${snapshotKey}`;
  indicatorParamsSnapshot[snapshotKey] = params;
  try {
    await configApi.setConfigKey({
      key: backendKey,
      value: JSON.stringify(params),
      name: CHART_GROUP,
      // 同上：动态键描述由写入方携带
      description: INDICATOR_PARAMS_DESCRIPTION,
    });
    try {
      localStorage.removeItem(legacyIndicatorParamsKey(symbolCode, indicatorId));
    } catch {
      // 清理旧键失败无碍
    }
  } catch (error) {
    console.warn('[chartPreferences] 保存指标参数失败', error);
  }
};

/** 删除后端 priceStyle（恢复默认）；uiPrefs/指标参数是记忆性质，不参与恢复默认 */
export const restorePriceStyle = async (): Promise<void> => {
  cancelPendingSaves();
  priceStyleServer = {};
  try {
    await configApi.deleteConfigKey('priceStyle');
  } catch (error) {
    console.warn('[chartPreferences] 清除图表样式配置失败', error);
  }
};

/** 页面层挂载后读 uiPrefs 快照（含迁移来的旧 localStorage 值） */
export const getUiPrefsSnapshot = (): ChartUiPrefs => ({ ...uiPrefsServer });
