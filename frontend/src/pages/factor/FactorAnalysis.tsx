/**
 * 因子分析页面容器：主 Tab [因子库 | 因子对比]
 *
 * 因子库为左右主从：
 * - catalog 由本容器单次拉取，是左右两栏唯一数据源；
 * - 选中决策链：?factor=（命中才生效）> localStorage.factor.lastViewed > catalog[0] > null；
 * - tab/factor 变更一律 replace，切 tab 保留 factor；右栏按 factor.name 加 key，切因子整体重挂载。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App as AntApp, Flex, Tabs } from 'antd';
import { useSearchParams } from 'react-router-dom';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import { factorApi, type FactorCatalogItem } from '@/api/factor';
import FactorCompare from './FactorCompare';
import FactorLibraryPane from './FactorLibraryPane';
import FactorDetailPane from './FactorDetailPane';
import MineLLMDrawer from './MineLLMDrawer';

const TAB_KEYS = ['library', 'compare'] as const;
const LAST_VIEWED_KEY = 'factor.lastViewed';

const FactorAnalysis: React.FC = () => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = TAB_KEYS.includes(searchParams.get('tab') as (typeof TAB_KEYS)[number])
    ? (searchParams.get('tab') as (typeof TAB_KEYS)[number])
    : 'library';

  const [catalog, setCatalog] = useState<FactorCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [mineOpen, setMineOpen] = useState(false);
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

  // LLM 挖掘保存成功：关抽屉 → 刷新目录 → 选中新因子（落概览，不自动分析）
  const handleMined = useCallback(
    async (name: string) => {
      setMineOpen(false);
      try {
        await loadCatalog();
      } catch {
        // 刷新失败仍选中（名字本地已知），左栏待下次刷新可见
        message.warning(t('factor_lib_load_failed') || '因子库刷新失败，新因子稍后可见');
      }
      decidedRef.current = true;
      setSelected(name);
    },
    [loadCatalog, t],
  );

  const selectedFactor = catalog.find((f) => f.name === selected) ?? null;

  return (
    <PageContainer title={t('factor_analysis')}>
      <Tabs
        activeKey={tab}
        onChange={switchTab}
        items={[
          {
            key: 'library',
            label: t('factor_library'),
            children: (
              <Flex gap="middle" align="flex-start">
                <div style={{ width: 480, flex: '0 0 auto' }}>
                  <FactorLibraryPane
                    catalog={catalog}
                    loading={loading}
                    loadError={loadError}
                    selected={selected}
                    onSelect={setSelected}
                    onRefresh={loadCatalog}
                    onMine={() => setMineOpen(true)}
                  />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* key 保证切因子时右栏三页签与表单/结果整体重置回概览 */}
                  <FactorDetailPane
                    key={selectedFactor?.name ?? 'empty'}
                    factor={selectedFactor}
                    onRefreshCatalog={() => void loadCatalog()}
                  />
                </div>
              </Flex>
            ),
          },
          { key: 'compare', label: t('factor_compare'), children: <FactorCompare /> },
        ]}
      />
      <MineLLMDrawer open={mineOpen} onClose={() => setMineOpen(false)} onMined={(n) => void handleMined(n)} />
    </PageContainer>
  );
};

export default FactorAnalysis;
