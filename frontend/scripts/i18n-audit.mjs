#!/usr/bin/env node
/**
 * i18n 硬编码中文审计（O6，i18n 完整性审计门禁）
 *
 * 扫描 src/pages、src/components、src/utils 下的 tsx/ts 文件中的硬编码中文字面量，
 * 按 file 排行输出。三种模式：
 *   node scripts/i18n-audit.mjs                # 探测：输出排行（默认）
 *   node scripts/i18n-audit.mjs --check        # 门禁：各文件计数不得超过 baseline，超标 exit 1
 *   node scripts/i18n-audit.mjs --update-baseline  # 重写 baseline（迁移推进后基线应只降不升）
 *
 * baseline 存 scripts/i18n-audit-baseline.json；--check 保证"清零增长"：
 * 新增硬编码会让 CI/本地门禁变红，迁出词条后主动 --update-baseline 收紧基线。
 *
 * ponytail: 行级正则排除注释，跨行块注释体内的中文会误报——探测器允许少量误报，
 * 升级路径：换 AST 解析（@babel/parser）。
 */
import { readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = fileURLToPath(new URL('.', import.meta.url))
const frontendRoot = join(scriptDir, '..')
const srcDir = join(frontendRoot, 'src')
const baselinePath = join(scriptDir, 'i18n-audit-baseline.json')

const args = process.argv.slice(2)
const checkMode = args.includes('--check')
const updateBaseline = args.includes('--update-baseline')

const CJK_RE = /[\u4e00-\u9fff]/
// 行级注释排除：JSX 注释 {/* */}、单行 //、块注释 /* 与续行 *
const COMMENT_LINE_RE = /^\s*(\{?\/\*|\*|\/\/)/
const SCAN_DIRS = ['pages', 'components', 'utils']

// 递归收集 .tsx/.ts 文件（跳过 .d.ts 与测试）
function walk(dir, out = []) {
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, name.name)
    if (name.isDirectory()) {
      walk(full, out)
    } else if (/\.(tsx?|mjs)$/.test(name.name) && !/\.d\.ts$|\.test\./.test(name.name)) {
      out.push(full)
    }
  }
  return out
}

const results = []
for (const sub of SCAN_DIRS) {
  const dir = join(srcDir, sub)
  if (!existsSync(dir)) continue
  for (const file of walk(dir)) {
    const lines = readFileSync(file, 'utf-8').split('\n')
    let count = 0
    for (const line of lines) {
      if (COMMENT_LINE_RE.test(line)) continue
      // 行尾注释同样不计文案（如行内 // 说明）。要求注释符前有空白，避免误伤字符串里的 https://
      const code = line.replace(/\s+\/\/.*$/, '').replace(/\s+\{?\/\*[\s\S]*?\*\/\s*$/, '')
      if (CJK_RE.test(code)) count++
    }
    if (count > 0) results.push({ file: relative(frontendRoot, file), count })
  }
}

results.sort((a, b) => b.count - a.count)
const total = results.reduce((s, r) => s + r.count, 0)

function printReport() {
  console.log(`\ni18n 硬编码中文审计：共 ${total} 行（${SCAN_DIRS.join('/')}）\n`)
  for (const { file, count } of results) {
    console.log(`${String(count).padStart(5)}  ${file}`)
  }
  if (results.length === 0) console.log('（无硬编码中文，审计通过）')
  console.log('')
}

if (updateBaseline) {
  writeFileSync(baselinePath, JSON.stringify({ total, files: results }, null, 2) + '\n')
  console.log(`baseline 已更新：${total} 行硬编码中文（${baselinePath}）`)
  process.exit(0)
}

if (!checkMode) {
  printReport()
  process.exit(0)
}

// --check 门禁模式：与 baseline 比对，任何文件计数上涨或新增文件即失败
if (!existsSync(baselinePath)) {
  console.error('未找到 baseline，请先执行: bun run i18n:audit --update-baseline')
  process.exit(1)
}
const baseline = JSON.parse(readFileSync(baselinePath, 'utf-8'))
const violations = []
const baselineMap = new Map(baseline.files.map((f) => [f.file, f.count]))
for (const { file, count } of results) {
  const allowed = baselineMap.get(file)
  if (allowed === undefined || count > allowed) {
    violations.push(`${file}: ${count} 行（基线 ${allowed ?? '新文件, 0'}）`)
  }
}
if (violations.length > 0) {
  console.error(`\ni18n 审计失败：以下文件硬编码中文超出基线（只许迁移减少，不许新增）：\n`)
  for (const v of violations) console.error(`  ${v}`)
  console.error(`\n处理方式：把硬编码中文迁至 i18n 词条；若确为合理基线收紧后请跑 --update-baseline\n`)
  process.exit(1)
}
console.log(`i18n 审计通过：${total} 行硬编码中文，均在基线内（基线总量 ${baseline.total}，迁移推进后用 --update-baseline 收紧）`)
