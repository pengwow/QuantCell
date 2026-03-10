import { useState, useCallback, useRef } from 'react';
import { message } from 'antd';
import { aiModelApi, type StrategyGenerateRequest, type ThinkingChainEventData, type CodeValidationRequest, type StrategyTemplate } from '../api';
import { useTranslation } from 'react-i18next';

/**
 * 思维链步骤
 */
export interface ThinkingStep {
  title: string;
  description: string;
  status: 'pending' | 'active' | 'completed';
}

/**
 * 生成结果
 */
export interface GenerationResult {
  code: string;
  explanation: string;
  modelUsed: string;
  tokensUsed: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
}

/**
 * 策略生成Hook返回类型
 */
export interface UseStrategyGenerationReturn {
  // 状态
  isGenerating: boolean;
  thinkingSteps: ThinkingStep[];
  generatedContent: string;
  generatedCode: string;
  result: GenerationResult | null;
  error: Error | null;
  
  // 方法
  generateStrategy: (requirement: string, modelId?: string, temperature?: number) => Promise<void>;
  validateCode: (code: string) => Promise<{ valid: boolean; errors: string[]; warnings: string[] }>;
  getTemplates: (category?: string) => Promise<StrategyTemplate[]>;
  cancelGeneration: () => void;
  reset: () => void;
}

/**
 * 策略生成Hook
 * 
 * 封装策略生成的完整逻辑，包括：
 * - 流式响应处理
 * - 思维链状态管理
 * - 代码提取和验证
 * - 错误处理
 * 
 * @example
 * ```tsx
 * const {
 *   isGenerating,
 *   thinkingSteps,
 *   generatedCode,
 *   generateStrategy,
 *   validateCode,
 * } = useStrategyGeneration();
 * 
 * // 生成策略
 * await generateStrategy('创建一个双均线交叉策略');
 * 
 * // 验证代码
 * const validation = await validateCode(generatedCode);
 * ```
 */
export function useStrategyGeneration(): UseStrategyGenerationReturn {
  const { t } = useTranslation();
  
  // 状态
  const [isGenerating, setIsGenerating] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([
    { title: t('thinking_analyze') || '分析需求', description: t('thinking_analyze_desc') || '理解您的策略需求', status: 'pending' },
    { title: t('thinking_design') || '设计策略', description: t('thinking_design_desc') || '设计策略结构和逻辑', status: 'pending' },
    { title: t('thinking_generate') || '生成代码', description: t('thinking_generate_desc') || '编写策略代码', status: 'pending' },
    { title: t('thinking_optimize') || '优化代码', description: t('thinking_optimize_desc') || '优化代码性能', status: 'pending' },
  ]);
  const [generatedContent, setGeneratedContent] = useState('');
  const [generatedCode, setGeneratedCode] = useState('');
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [error, setError] = useState<Error | null>(null);
  
  // 取消控制器
  const cancelRef = useRef<(() => void) | null>(null);
  
  /**
   * 更新思维链步骤状态
   */
  const updateStepStatus = useCallback((stepIndex: number, status: 'active' | 'completed') => {
    setThinkingSteps(prev => prev.map((step, idx) => 
      idx === stepIndex ? { ...step, status } : step
    ));
  }, []);
  
  /**
   * 从内容中提取代码块
   */
  const extractCode = useCallback((content: string): string => {
    // 匹配 ```python ... ``` 格式的代码块
    const pythonCodeRegex = /```python\n([\s\S]*?)\n```/;
    const match = content.match(pythonCodeRegex);
    if (match) {
      return match[1].trim();
    }
    
    // 匹配 ``` ... ``` 格式的代码块
    const genericCodeRegex = /```\n([\s\S]*?)\n```/;
    const genericMatch = content.match(genericCodeRegex);
    if (genericMatch) {
      return genericMatch[1].trim();
    }
    
    return '';
  }, []);
  
  /**
   * 生成策略
   * 
   * @param requirement 策略需求描述
   * @param modelId 模型ID（可选）
   * @param temperature 温度参数（可选）
   */
  const generateStrategy = useCallback(async (
    requirement: string,
    modelId?: string,
    temperature?: number
  ): Promise<void> => {
    if (!requirement.trim()) {
      message.warning(t('input_empty') || '请输入策略需求');
      return;
    }
    
    // 重置状态
    setIsGenerating(true);
    setError(null);
    setGeneratedContent('');
    setGeneratedCode('');
    setResult(null);
    setThinkingSteps(prev => prev.map(step => ({ ...step, status: 'pending' })));
    
    const requestData: StrategyGenerateRequest = {
      requirement: requirement.trim(),
      model_id: modelId,
      temperature,
    };
    
    try {
      // 使用优化后的流式生成（思维链实时，代码一次性返回）
      cancelRef.current = aiModelApi.generateStrategyStream(
        requestData,
        // onThinkingChain - 思维链进度实时更新
        (data: ThinkingChainEventData) => {
          // 根据当前步骤更新思维链状态
          if (data.current_step === 1) {
            updateStepStatus(0, 'active');
          } else if (data.current_step === 2) {
            updateStepStatus(0, 'completed');
            updateStepStatus(1, 'active');
          } else if (data.current_step === 3) {
            updateStepStatus(1, 'completed');
            updateStepStatus(2, 'active');
          } else if (data.current_step === 4) {
            updateStepStatus(2, 'completed');
            updateStepStatus(3, 'active');
          }
        },
        // onDone - 生成完成，一次性返回完整结果
        (result: { code?: string; raw_content?: string; metadata?: any }) => {
          updateStepStatus(3, 'completed');
          
          // 提取代码
          const finalContent = result.raw_content || '';
          const code = result.code || extractCode(finalContent);
          setGeneratedCode(code);
          
          // 设置结果
          if (result.metadata) {
            setResult({
              code,
              explanation: finalContent.replace(/```python\n[\s\S]*?\n```/g, '').trim(),
              modelUsed: result.metadata.model || '',
              tokensUsed: {
                promptTokens: result.metadata.tokens_used?.prompt_tokens || 0,
                completionTokens: result.metadata.tokens_used?.completion_tokens || 0,
                totalTokens: result.metadata.tokens_used?.total_tokens || 0,
              },
            });
          }
          
          setIsGenerating(false);
          message.success(t('generate_success') || '策略生成成功');
        },
        // onError - 错误处理
        (err: Error) => {
          // 错误处理
          console.error('策略生成错误:', err);
          setError(err);
          setIsGenerating(false);
          message.error(err.message || t('generate_error') || '策略生成失败');
        }
      );
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error('策略生成异常:', error);
      setError(error);
      setIsGenerating(false);
      message.error(error.message || t('generate_error') || '策略生成失败');
    }
  }, [t, updateStepStatus, extractCode, generatedContent]);
  
  /**
   * 验证代码
   * 
   * @param code 代码字符串
   * @returns 验证结果
   */
  const validateCode = useCallback(async (
    code: string
  ): Promise<{ valid: boolean; errors: string[]; warnings: string[] }> => {
    if (!code.trim()) {
      return { valid: false, errors: ['代码不能为空'], warnings: [] };
    }
    
    try {
      const requestData: CodeValidationRequest = {
        code: code.trim(),
        language: 'python',
      };
      
      const response = await aiModelApi.validateCode(requestData);
      
      const errors = response.errors.map(e => `第${e.line}行: ${e.message}`);
      const warnings = response.warnings.map(w => `第${w.line}行: ${w.message}`);
      
      if (response.valid) {
        message.success(t('validate_success') || '代码验证通过');
      } else {
        message.error(t('validate_failed') || '代码验证失败');
      }
      
      return {
        valid: response.valid,
        errors,
        warnings,
      };
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error('代码验证错误:', error);
      message.error(error.message || t('validate_error') || '代码验证失败');
      return {
        valid: false,
        errors: [error.message],
        warnings: [],
      };
    }
  }, [t]);
  
  /**
   * 获取策略模板列表
   * 
   * @param category 分类ID
   * @returns 模板列表
   */
  const getTemplates = useCallback(async (category?: string): Promise<StrategyTemplate[]> => {
    try {
      const templates = await aiModelApi.getTemplates(category);
      return templates;
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error('获取模板列表错误:', error);
      message.error(t('get_templates_error') || '获取模板列表失败');
      return [];
    }
  }, [t]);
  
  /**
   * 取消生成
   */
  const cancelGeneration = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }
    setIsGenerating(false);
    message.info(t('generate_cancelled') || '已取消生成');
  }, [t]);
  
  /**
   * 重置状态
   */
  const reset = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }
    setIsGenerating(false);
    setThinkingSteps([
      { title: t('thinking_analyze') || '分析需求', description: t('thinking_analyze_desc') || '理解您的策略需求', status: 'pending' },
      { title: t('thinking_design') || '设计策略', description: t('thinking_design_desc') || '设计策略结构和逻辑', status: 'pending' },
      { title: t('thinking_generate') || '生成代码', description: t('thinking_generate_desc') || '编写策略代码', status: 'pending' },
      { title: t('thinking_optimize') || '优化代码', description: t('thinking_optimize_desc') || '优化代码性能', status: 'pending' },
    ]);
    setGeneratedContent('');
    setGeneratedCode('');
    setResult(null);
    setError(null);
  }, [t]);
  
  return {
    isGenerating,
    thinkingSteps,
    generatedContent,
    generatedCode,
    result,
    error,
    generateStrategy,
    validateCode,
    getTemplates,
    cancelGeneration,
    reset,
  };
}

export default useStrategyGeneration;
