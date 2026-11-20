/**
 * 编辑器状态栏（design-spec §6.16）：`#007acc` 底、10.5px mono、末项「Spaces: 4」靠右。
 *
 * 三处 Monaco 使用点（策略编辑器 / 因子代码面板 / 因子表单弹窗）共用，
 * 避免各写一份内联样式导致 padding 与字号漂移。
 */
import { QC_EDITOR_FONT_FAMILY } from './quantcellTheme';

const barStyle: React.CSSProperties = {
  display: 'flex',
  gap: 14,
  padding: '3px 14px',
  background: '#007acc',
  color: '#ffffff',
  fontFamily: QC_EDITOR_FONT_FAMILY,
  fontSize: 10.5,
  lineHeight: '16px',
  userSelect: 'none',
};

interface Props {
  /** 真实光标位置（来自 onDidChangeCursorPosition，别写死） */
  line: number;
  column: number;
}

const QcEditorStatusBar = ({ line, column }: Props) => (
  <div style={barStyle}>
    <span>Python</span>
    <span>UTF-8</span>
    <span>{`Ln ${line}, Col ${column}`}</span>
    <span style={{ marginLeft: 'auto' }}>Spaces: 4</span>
  </div>
);

export default QcEditorStatusBar;
