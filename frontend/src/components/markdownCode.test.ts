// markdownCode 纯函数校验：代码围栏剔除 + 块级/行内判定
import { describe, expect, it } from 'vitest';
import { isBlockCode, stripDuplicatedCodeBlock } from './markdownCode';

describe('stripDuplicatedCodeBlock', () => {
  // 新策略：无脑删所有围栏块（卡片 desc 专用兜底——result-code 已经是完整代码，
  // desc 里任何围栏都是冗余残留，错删风险为零）
  const code = 'def ma():\n    return 1';

  it('删除完整代码围栏块', () => {
    const content = `以下是策略代码：\n\n\`\`\`python\n${code}\n\`\`\`\n\n参数可调整。`;
    expect(stripDuplicatedCodeBlock(content, `${code}\n`)).toBe('以下是策略代码：\n\n参数可调整。');
  });

  it('无语言标记的 fence 同样被删', () => {
    const content = `说明\n\n\`\`\`\n${code}\n\`\`\``;
    expect(stripDuplicatedCodeBlock(content, code)).toBe('说明');
  });

  it('碎片围栏（docstring 残余）也被删', () => {
    const content = `策略概述\n\n\`\`\`\n交易逻辑：RSI <= oversold 开多\n\`\`\``;
    expect(stripDuplicatedCodeBlock(content, code)).toBe('策略概述');
  });

  it('非 Python 语言围栏也被删（desc 里本来不该有代码）', () => {
    const content = '```python\nprint("别的代码")\n```\n\n说明';
    expect(stripDuplicatedCodeBlock(content, code)).toBe('说明');
  });

  it('多个围栏块全部删除，只留说明', () => {
    const content = `\`\`\`python\n${code}\n\`\`\`\n\n前置示例：\n\n\`\`\`python\nprint(1)\n\`\`\``;
    expect(stripDuplicatedCodeBlock(content, code)).toBe('前置示例：');
  });

  it('行内 fence（模型偶发）也删除', () => {
    const content = '用 ```python``` 模块做计算';
    expect(stripDuplicatedCodeBlock(content, code)).toBe('用  模块做计算');
  });

  it('空 content 直接返回', () => {
    expect(stripDuplicatedCodeBlock('', code)).toBe('');
  });

  it('无围栏的纯说明原样保留', () => {
    expect(stripDuplicatedCodeBlock('这是一段说明文字', code)).toBe('这是一段说明文字');
  });

  it('全部是围栏块 → 返回空', () => {
    const content = `\`\`\`python\n${code}\n\`\`\``;
    expect(stripDuplicatedCodeBlock(content, code)).toBe('');
  });
});

describe('isBlockCode', () => {
  it('带 language- 前缀判定为块级', () => {
    expect(isBlockCode('language-python', 'x')).toBe(true);
  });

  it('多行内容判定为块级', () => {
    expect(isBlockCode(undefined, 'a\nb')).toBe(true);
  });

  it('单行无语言前缀判定为行内', () => {
    expect(isBlockCode(undefined, 'foo')).toBe(false);
    expect(isBlockCode('', '')).toBe(false);
  });
});
