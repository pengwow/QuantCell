// AI 对话 Markdown 的代码块工具：重复代码剔除 + 行内/块级判定

/**
 * 剔除说明文案中所有 fence 代码块（卡片 desc 专用兜底）。
 *
 * 结果卡片下方已用 CodeView 单独展示完整代码，说明文案里出现的任何 fence
 * （无论内容是完整代码、碎片 docstring、还是 ```\n交易逻辑：...``` 这种
 * 无语言围栏碎片）都是冗余残留，直接删掉即可。
 *
 * ponytail: 历史版本只删「与 code 完全一致」的块，对碎片围栏/裸代码完全无效；
 * 改无脑删所有 fence 更鲁棒——desc 里本来就不该有代码，错删风险为零。
 */
export function stripDuplicatedCodeBlock(content: string, _code: string): string {
  if (!content) return content;
  return content
    // 删掉所有围栏代码块（含 ```python / ``` / ```` 等 3+ 反引号变体）
    .replace(/`{3,}[^\n]*\n[\s\S]*?`{3,}/g, '')
    // 删掉所有行内 ```code``` 样式（模型偶发把代码片段包在单行 fence 里）
    .replace(/`{3,}[^`\n]*`{3,}/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * 判定 markdown code 节点是块级 fence 还是行内代码
 * react-markdown v10 的 components.code 同时接管两种节点，已无 inline prop 可用。
 * ponytail: 以「language- 前缀或内容含换行」启发式分流——行内代码跨行极罕见；
 * 若出现误判，升级路径是接管 pre 组件按父节点分流。
 */
export function isBlockCode(className: string | undefined, children: unknown): boolean {
  if (className?.includes('language-')) return true;
  return String(children).includes('\n');
}
