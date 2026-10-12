import { apiRequest } from './index';

/** AI 文本润色目标类型 */
export type AIPolishTarget = 'label' | 'description' | 'name' | 'summary';

export interface AIPolishParams {
  target: AIPolishTarget;
  context: Record<string, unknown>;
  max_length?: number;
  model_id?: string;
}

export interface AIPolishResult {
  content: string;
}

export const aiApi = {
  /** 通用 AI 短文本生成（label/description/name/summary），支持长度限制 */
  polish: (p: AIPolishParams) =>
    apiRequest.post<AIPolishResult>('/ai/polish', p),
};
