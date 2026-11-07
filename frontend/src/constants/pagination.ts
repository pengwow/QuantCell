/**
 * 全局分页档位常量
 *
 * 全站列表/卡片页共用一套分页档位（系统设置 → 通用设置 里的
 * "每页显示数量" 下拉即用此档位，切换会持久化到后端配置）。
 * 档位取 12 的倍数（12 = 1/2/3/4 列网格的公倍数），保证卡片网格
 * 在常见列数下不出现残行。
 */
export const PAGE_SIZE_OPTIONS = ['12', '24', '36', '48', '96'];

// 数字版档位，供 antd Pagination 的 pageSizeOptions（number[]）使用
export const PER_PAGE_OPTIONS = PAGE_SIZE_OPTIONS.map(Number);

/**
 * 将任意页大小吸附到最近的 12 的倍数（最小 12）。
 * 用于兼容历史存量配置（如 defaultPerPage=10/15/100）平滑迁移到新档位。
 */
export const snapPageSize = (n: number): number =>
  Math.max(12, Math.round(n / 12) * 12);
