// Worker 名称自动生成：策略名 + 超短唯一码（创建 Worker 弹窗用）
// 纯函数抽出便于单测；冲突判定由调用方传入现有名单（含大小写归一）。

// 去掉混淆字符（0/o、1/l/i）的 base36 小写字母表，4 位即可 30^4≈81 万组合
const CODE_ALPHABET = '23456789abcdefghjkmnpqrstuvwxyz';

const randomCode = (len: number): string => {
  let s = '';
  for (let i = 0; i < len; i++) {
    s += CODE_ALPHABET[Math.floor(Math.random() * CODE_ALPHABET.length)];
  }
  return s;
};

/**
 * 生成不与现有 Worker 冲突的名称：`<策略名>_<短码>`。
 * 策略名空白时回退为 'worker'；连撞 10 次则加长到 6 位（理论不会发生）。
 */
export function buildWorkerName(strategyName: string, takenNames: Iterable<string>): string {
  const base = (strategyName || '').trim() || 'worker';
  const taken = new Set([...takenNames].map((n) => n.trim().toLowerCase()));
  for (const len of [4, 6]) {
    for (let i = 0; i < 10; i++) {
      const candidate = `${base}_${randomCode(len)}`;
      if (!taken.has(candidate.toLowerCase())) return candidate;
    }
  }
  return `${base}_${randomCode(4)}_${Date.now().toString(36)}`;
}
