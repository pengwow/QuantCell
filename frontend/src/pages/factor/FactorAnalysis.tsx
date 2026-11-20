/**
 * 因子分析页面容器：页头（标题 + 真实聚合副标 + 新建因子）+ 主 Tab [因子库 | 因子对比]
 *
 * 因子库为左右主从：
 * - catalog 由本容器单次拉取，是左右两栏唯一数据源；
 * - 选中决策链：?factor=（命中才生效）> localStorage.factor.lastViewed > catalog[0] > null；
 * - tab/factor 变更一律 replace，切 tab 保留 factor；右栏按 factor.name 加 key，切因子整体重挂载。
 * - 副标（demo 口径）：按 lifecycle_status 聚合「因子库 N 个 · 有效 x · 观察 y · 失效 z」，
 *   分组规则见 statusGroupOf（与 FactorLibraryPane 的筛选 chips 同一字段；接口未提供
 *   样本/IC 频率口径，demo 的「样本 1h 全品种 · RankIC（日频）」不写，避免编造）。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App as AntApp, Button, Drawer, Tabs } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { factorApi, type FactorCatalogItem } from '@/api/factor';
import FactorCompare from './FactorCompare';
import FactorLibraryPane from './FactorLibraryPane';
import FactorDetailPane from './FactorDetailPane';

const TAB_KEYS = ['library', 'compare'] as const;
const LAST_VIEWED_KEY = 'factor.lastViewed';

/** 生命周期 → 演示分组（有效/观察/失效）：与 FactorLibraryPane 的筛选 chips 同一规则 */
const statusGroupOf = (s: FactorCatalogItem['lifecycle_status']): 'active' | 'watch' | 'retired' =>
  s === 'LIVE' ? 'active' : s === 'RETIRED' ? 'retired' : 'watch';

const FactorAnalysis: React.FC = () => {
  const { t } = useTranslation();
  AntApp.useApp(); // 仅为触发 App 全局注入（message 能力由子组件按需 useApp）
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = TAB_KEYS.includes(searchParams.get('tab') as (typeof TAB_KEYS)[number])
    ? (searchParams.get('tab') as (typeof TAB_KEYS)[number])
    : 'library';

  const [catalog, setCatalog] = useState<FactorCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  // 初始选中只决策一次，避免 StrictMode/刷新重复回退
  const decidedRef = useRef(false);

  useEffect(() => {
    setPageTitle(t('factor_analysis'));
  }, [t]);

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      setCatalog((await factorApi.catalog()).factors);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  // catalog 首次就绪后按决策链确定选中因子
  useEffect(() => {
    if (loading || loadError || decidedRef.current) return;
    decidedRef.current = true;
    const has = (n: string | null): n is string => !!n && catalog.some((f) => f.name === n);
    const urlName = searchParams.get('factor');
    const lastViewed = localStorage.getItem(LAST_VIEWED_KEY);
    setSelected(has(urlName) ? urlName : has(lastViewed) ? lastViewed : (catalog[0]?.name ?? null));
    // 仅在 catalog 首帧决策一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, loading, loadError]);

  // 选中变化 → 记忆 + URL replace（不依赖 searchParams，避免写回触发自身重放）
  useEffect(() => {
    if (selected == null) return;
    localStorage.setItem(LAST_VIEWED_KEY, selected);
    if (searchParams.get('factor') === selected) return;
    const next = new URLSearchParams(searchParams);
    next.set('factor', selected);
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  // 当前选中因子被删除（catalog 刷新后消失）→ 回退列表第一个，无则 null
  useEffect(() => {
    if (!decidedRef.current || selected == null) return;
    if (!catalog.some((f) => f.name === selected)) {
      setSelected(catalog[0]?.name ?? null);
    }
  }, [catalog, selected]);

  const switchTab = useCallback(
    (key: string) => {
      // 切 tab 保留 factor，只替换 tab 参数
      const next = new URLSearchParams(searchParams);
      next.set('tab', key);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  // 副标：按生命周期聚合（LIVE=有效 / DISCOVERED·INSPECTED·PAPER_TRADING=观察 / RETIRED=失效），
  // 只在成功加载后展示，加载失败不编造数字
  const subtitle = useMemo(() => {
    if (loadError || loading) return undefined;
    const active = catalog.filter((f) => statusGroupOf(f.lifecycle_status) === 'active').length;
    const retired = catalog.filter((f) => statusGroupOf(f.lifecycle_status) === 'retired').length;
    return t('factor_sub_status', {
      total: catalog.length,
      active,
      watch: catalog.length - active - retired,
      retired,
    });
  }, [catalog, loadError, loading, t]);

  const selectedFactor = catalog.find((f) => f.name === selected) ?? null;

  return (
    <PageContainer
      title={t('factor_analysis')}
      subtitle={subtitle}
      actions={
        // demo page-actions：新建因子（主色 30px 钮，与回测中心「发起回测」同款）
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateOpen(true)}
          style={{ height: 30, padding: '0 12px', fontSize: 12, fontWeight: 550 }}
        >
          {t('factor_lib_create_btn')}
        </Button>
      }
    >
      <Tabs
        activeKey={tab}
        onChange={switchTab}
        items={[
          {
            key: 'library',
            label: t('factor_library'),
            children: (
              <>
                <FactorLibraryPane
                  catalog={catalog}
                  loading={loading}
                  loadError={loadError}
                  selected={selected}
                  onSelect={(name) => {
                    setSelected(name);
                    setDetailOpen(true);
                  }}
                  onRefresh={loadCatalog}
                  onCreate={() => setCreateOpen(true)}
                  createVisible={createOpen}
                  onCloseCreate={() => setCreateOpen(false)}
                />
                <Drawer
                  open={detailOpen}
                  size="68%"
                  push
                  destroyOnHidden
                  closable
                  placement="right"
                  onClose={() => setDetailOpen(false)}
                >
                  <FactorDetailPane
                    key={selectedFactor?.name ?? 'empty'}
                    factor={selectedFactor}
                    onRefreshCatalog={() => void loadCatalog()}
                  />
                </Drawer>
              </>
            ),
          },
          { key: 'compare', label: t('factor_compare'), children: <FactorCompare /> },
        ]}
      />
    </PageContainer>
  );
};

export default FactorAnalysis;
