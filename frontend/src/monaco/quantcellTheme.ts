/**
 * Monaco 主题 `quantcell-dark` —— design-spec §6.16「代码编辑器 chrome」。
 *
 * 编辑器 chrome 恒深色，不随 light/dark 主题切换：底色 #1e1e1e、行号列 #252526/#858585、
 * token 色按 VS Code Dark+ 语义表。三处 Monaco 使用点（策略编辑器 / 因子代码面板 /
 * 因子表单弹窗）统一走这里，避免各自写一套 theme 字符串。
 */
import type { editor } from 'monaco-editor';
import type { Monaco } from '@monaco-editor/react';

export const QC_THEME_NAME = 'quantcell-dark';

/** 编辑器底（与 token 区同色，用于包裹层避免亮色主题下露白） */
export const QC_EDITOR_BG = '#1e1e1e';
/** 容器几何（§6.16）：10px 圆角 + 1px 边框，与基准 demo 的 .ced 一致 */
export const QC_EDITOR_RADIUS = 10;
export const QC_EDITOR_BORDER = '1px solid var(--qc-border)';
export const QC_EDITOR_FONT_FAMILY = 'ui-monospace, SFMono-Regular, Menlo, monospace';
export const QC_EDITOR_FONT_SIZE = 12.5;
export const QC_EDITOR_LINE_HEIGHT = 19;

export const QUANTCELL_DARK: editor.IStandaloneThemeData = {
  base: 'vs-dark',
  inherit: true,
  rules: [
    // 注释：Dark+ 绿 + 斜体
    { token: 'comment', foreground: '6a9955', fontStyle: 'italic' },
    { token: 'comment.doc', foreground: '6a9955', fontStyle: 'italic' },
    // 关键字：控制流紫。Python 的 Monarch 文法把 def/class/import 也归入同一个 `keyword`
    // token，无法复刻 VS Code 里 def/class 的 #569cd6 —— #569cd6 系留给能区分子类的文法
    // （预处理器 directive / keyword.other），其余继承 base vs-dark。
    { token: 'keyword', foreground: 'c586c0' },
    { token: 'keyword.control', foreground: 'c586c0' },
    { token: 'keyword.directive', foreground: '569cd6' },
    { token: 'keyword.other', foreground: '569cd6' },
    // 字符串 / 引号：Python 的 Monarch 把开闭引号也归为 string.escape，统一成字符串色
    // （VS Code 里引号与正文同色，转义序列才偏黄；这里不追那点差异）
    { token: 'string', foreground: 'ce9178' },
    { token: 'string.escape', foreground: 'ce9178' },
    { token: 'regexp', foreground: 'd16969' },
    // 数字
    { token: 'number', foreground: 'b5cea8' },
    { token: 'number.hex', foreground: 'b5cea8' },
    { token: 'number.float', foreground: 'b5cea8' },
    // 函数名
    { token: 'function', foreground: 'dcdcaa' },
    { token: 'entity.name.function', foreground: 'dcdcaa' },
    // 类型 / 类名
    { token: 'type', foreground: '4ec9b0' },
    { token: 'type.identifier', foreground: '4ec9b0' },
    { token: 'entity.name.type', foreground: '4ec9b0' },
    // 变量 / 标识符
    { token: 'variable', foreground: '9cdcfe' },
    { token: 'variable.name', foreground: '9cdcfe' },
    { token: 'identifier', foreground: '9cdcfe' },
    { token: 'attribute.name', foreground: '9cdcfe' },
    // 常量 / 特殊字面量
    { token: 'constant', foreground: '4fc1ff' },
    { token: 'keyword.json', foreground: '9cdcfe' },
  ],
  colors: {
    'editor.background': '#1e1e1e',
    'editor.foreground': '#d4d4d4',
    'editorLineNumber.foreground': '#858585',
    'editorLineNumber.activeForeground': '#c6c6c6',
    'editorGutter.background': '#252526',
    'editor.selectionBackground': '#264f78',
    'editor.lineHighlightBackground': '#2a2d2e',
    'editorCursor.foreground': '#aeafad',
    'editorIndentGuide.background1': '#404040',
    // Monaco 默认开启成对括号配色，会把 () 染金、[] 染紫、{} 染粉；基准 demo 是单色括号，
    // 这里把 6 档括号色统一到默认前景，视觉与 demo 一致（匹配括号本身的高亮仍由 editorBracketMatch 负责）
    'editorBracketHighlight.foreground1': '#d4d4d4',
    'editorBracketHighlight.foreground2': '#d4d4d4',
    'editorBracketHighlight.foreground3': '#d4d4d4',
    'editorBracketHighlight.foreground4': '#d4d4d4',
    'editorBracketHighlight.foreground5': '#d4d4d4',
    'editorBracketHighlight.foreground6': '#d4d4d4',
    'editorBracketHighlight.unexpectedBracket.foreground': '#f14c4c',
    // 深色 chrome 里的控件也走深色，避免亮色主题下露白
    'editorWidget.background': '#252526',
    'editorSuggestWidget.background': '#252526',
    'editorSuggestWidget.selectedBackground': '#04395e',
    'scrollbarSlider.background': '#79797966',
    'scrollbarSlider.hoverBackground': '#646464b3',
    'scrollbarSlider.activeBackground': '#bfbfbf66',
  },
};

// ponytail: 模块级布尔足够 —— @monaco-editor/react 全局共用一个 loader 实例，
// 同页多个 <Editor> 共享 monaco 命名空间。若日后引入第二个 monaco 实例，改按实例缓存（WeakSet）。
let registered = false;

/** 幂等注册主题；直接传给 <Editor beforeMount={registerQuantcellTheme}> */
export function registerQuantcellTheme(monaco: Monaco): void {
  if (registered) return;
  monaco.editor.defineTheme(QC_THEME_NAME, QUANTCELL_DARK);
  registered = true;
}
