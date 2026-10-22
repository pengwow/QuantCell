// AI 策略生成 Chat Provider
// 将后端 /api/v1/ai-models/strategy/generate 的 SSE 流（thinking_chain / done / error 三类事件）
// 适配为 useXChat 可消费的消息流。遵循 x-chat-provider 四步法：只实现三个转换方法，请求动作交给框架。
import { AbstractChatProvider, XRequest } from '@ant-design/x-sdk';
import type {
  ChatProviderConfig,
  SSEOutput,
  TransformMessage,
  XRequestOptions,
} from '@ant-design/x-sdk';
import { handleUnauthorized } from '../api';
import type { ThinkingChainEventData } from '../api';
import { getAccessToken } from '../utils/tokenManager';

/** 后端 SSE 单个 data 事件的 JSON 结构 */
export interface StrategyStreamChunk {
  type: 'thinking_chain' | 'done' | 'error';
  data?: ThinkingChainEventData;
  code?: string;
  raw_content?: string;
  error?: string;
}

/** 聊天消息体（SimpleType 约束要求纯对象） */
export interface StrategyChatMessage {
  role: 'user' | 'ai';
  content: string;
  code?: string;
  failed?: boolean;
}

export interface StrategyChatInput {
  /** 发给后端的完整需求（可能带策略类型后缀） */
  requirement: string;
  /** 气泡里展示的原始用户输入（不含后缀），不传则用 requirement */
  displayContent?: string;
}

/** 思维链事件经 ref 抛给组件（transformMessage 只能返回消息，无法携带组件状态） */
export type ThinkingChainHandler = (data: ThinkingChainEventData) => void;

export interface ThinkingHandlerRef {
  current: ThinkingChainHandler | null;
}

type StrategyRequestClass = ChatProviderConfig<
  StrategyChatInput,
  SSEOutput,
  StrategyChatMessage
>['request'];

/** 请求实例：模块级创建，由 useXChat.onRequest 触发；401/非 2xx 在中间件统一处理 */
export const strategyChatRequest = XRequest<
  StrategyChatInput,
  SSEOutput,
  StrategyChatMessage
>('/api/v1/ai-models/strategy/generate', {
  // 必须手动模式：请求由 useXChat.onRequest 触发
  manual: true,
  middlewares: {
    // XRequest 走原生 fetch，不经过 axios 拦截器，需自行注入认证头
    onRequest: async (baseURL, options) => [
      baseURL,
      {
        ...options,
        headers: { ...options.headers, Authorization: `Bearer ${getAccessToken()}` },
      },
    ],
    onResponse: async (response) => {
      if (response.status === 401) {
        handleUnauthorized();
        throw new Error('登录已过期，请重新登录');
      }
      if (!response.ok) {
        // 透出后端错误体里的 message/detail，比裸状态码可读
        let errorMessage = `请求失败 (HTTP ${response.status})`;
        try {
          const errorData = await response.clone().json();
          errorMessage = errorData.message || errorData.detail || errorMessage;
        } catch {
          // 错误体非 JSON 时使用默认文案
        }
        throw new Error(errorMessage);
      }
      return response;
    },
  },
  callbacks: {
    // onSuccess 必填占位：消息终态由 useXChat 通过 provider.transformMessage 驱动，这里无需处理
    onSuccess: () => {},
    onError: (error) => {
      // AbortError 是主动取消（新请求顶掉旧流/关闭弹窗），静默即可；
      // 未配置 retryInterval，SDK 对非 AbortError 也不会自动重试
      if ((error as Error)?.name !== 'AbortError') {
        console.error('[StrategyChatProvider] 策略生成请求失败:', error);
      }
    },
  },
});

export class StrategyChatProvider extends AbstractChatProvider<
  StrategyChatMessage,
  StrategyChatInput,
  SSEOutput
> {
  private thinkingRef: ThinkingHandlerRef;

  constructor(config: { request: StrategyRequestClass; thinkingRef: ThinkingHandlerRef }) {
    super({ request: config.request });
    this.thinkingRef = config.thinkingRef;
  }

  // 只透传 requirement；model 不传时后端自动使用默认模型
  transformParams(
    requestParams: Partial<StrategyChatInput>,
    _options: XRequestOptions<StrategyChatInput, SSEOutput, StrategyChatMessage>,
  ): StrategyChatInput {
    return { requirement: requestParams.requirement || '' };
  }

  transformLocalMessage(requestParams: Partial<StrategyChatInput>): StrategyChatMessage {
    return { role: 'user', content: requestParams.displayContent || requestParams.requirement || '' };
  }

  transformMessage(info: TransformMessage<StrategyChatMessage, SSEOutput>): StrategyChatMessage {
    const { originMessage, chunk } = info;
    const placeholder = originMessage || { role: 'ai' as const, content: '' };

    // onSuccess 时框架以 chunk=undefined 再调一次，保留最后一次 onUpdate 的结果
    if (!chunk?.data) {
      return placeholder;
    }

    // chunk.data 是逐行的原始 JSON 字符串，坏行直接忽略（由 done/error 兜底）
    let event: StrategyStreamChunk;
    try {
      event = JSON.parse(chunk.data) as StrategyStreamChunk;
    } catch {
      return placeholder;
    }

    // 思维链只是过程提示：抛给组件渲染，消息保持空占位（气泡显示 loading 点）
    if (event.type === 'thinking_chain') {
      if (event.data) this.thinkingRef.current?.(event.data);
      return placeholder;
    }

    // SSE 带内错误事件（流正常结束，status 仍会走到 success，靠 failed 标记区分展示）
    if (event.type === 'error') {
      return { role: 'ai', content: event.error || '生成失败，请重试', code: '', failed: true };
    }

    // done：后端一次性返回完整结果（raw_content 为说明文案，code 为策略代码）
    const content = event.raw_content || '';
    const code = event.code || '';

    // [DEBUG] 临时调试：打印 done 事件实际字段，用户反馈"还有两个代码框"
    // 必须拿到前端实际收到的 content/code 才能确定畸形来源
    if (event.type === 'done') {
      const doneMeta = (event as unknown as { metadata?: Record<string, unknown> }).metadata;
      console.log('[AI策略 DEBUG done]', {
        raw_content_length: content.length,
        code_length: code.length,
        content,
        code,
        metadata: doneMeta,
      });
    }

    if (!content && !code) {
      // 空结果按失败处理，避免误显示"生成成功"
      return { role: 'ai', content: '模型未返回有效内容，请重试或更换模型', code: '', failed: true };
    }
    return { role: 'ai', content: content || code, code, failed: false };
  }
}
