/**
 * LLM 挖掘抽屉：左栏「LLM 挖掘」入口。FactorMining 保存因子后经 onMined 回调
 * 通知容器刷新目录并选中新因子（不再走 URL 跳转）。
 */
import { Drawer } from 'antd';
import { useTranslation } from 'react-i18next';
import FactorMining from './FactorMining';

const MineLLMDrawer: React.FC<{
  open: boolean;
  onClose: () => void;
  onMined: (name: string) => void;
}> = ({ open, onClose, onMined }) => {
  const { t } = useTranslation();
  return (
    <Drawer
      title={t('factor_mining') || 'LLM 挖掘'}
      open={open}
      onClose={onClose}
      size={1200}
      destroyOnHidden
      mask={{ closable: false }}
    >
      <FactorMining onMined={onMined} />
    </Drawer>
  );
};

export default MineLLMDrawer;
