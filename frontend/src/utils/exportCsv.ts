/**
 * CSV 导出工具
 *
 * 将对象数组转为 CSV 字符串并触发浏览器下载。
 * 默认支持千分位去除、UTF-8 BOM（Excel 中文兼容）。
 */

export interface CsvColumn<T> {
  /** 表头 */
  header: string
  /** 取值函数或字段名 */
  accessor: keyof T | ((row: T) => string | number | null | undefined)
}

const escapeCsvCell = (value: unknown): string => {
  if (value === null || value === undefined) return ''
  const str = String(value)
  // 需要转义：包含逗号、引号、换行
  if (/[",\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

export const buildCsv = <T>(rows: T[], columns: CsvColumn<T>[]): string => {
  const headerRow = columns.map((c) => escapeCsvCell(c.header)).join(',')
  const dataRows = rows.map((row) =>
    columns
      .map((col) => {
        const raw = typeof col.accessor === 'function' ? col.accessor(row) : row[col.accessor as keyof T]
        return escapeCsvCell(raw)
      })
      .join(',')
  )
  return [headerRow, ...dataRows].join('\n')
}

/**
 * 触发浏览器下载 CSV 文件
 * @param filename 文件名（不含扩展名）
 * @param rows 数据行
 * @param columns 列定义
 */
export const downloadCsv = <T>(filename: string, rows: T[], columns: CsvColumn<T>[]): void => {
  // 添加 UTF-8 BOM 以便 Excel 正确识别中文
  const csv = '\ufeff' + buildCsv(rows, columns)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename.endsWith('.csv') ? filename : `${filename}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * 生成带时间戳的文件名
 * @example timestampedFilename('worker_orders', 9) => "worker_orders_9_20260115T103000.csv"
 */
export const timestampedFilename = (prefix: string, ...parts: (string | number)[]): string => {
  const d = new Date()
  const pad = (n: number) => n.toString().padStart(2, '0')
  const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  return [prefix, ...parts, stamp].join('_') + '.csv'
}
