"""自动研究模块（Research Loop）。

P0 只实现 PRD §10 的闭环骨架：会话/试验/知识三张表、六步 deep 闭环、
quick 执行器映射、控制面、成本汇总与前端第三个 Tab。

依赖边界（借鉴分析 §7.3）：本包只允许 import pydantic / sqlalchemy / pandas /
axon_bridge / factor.*，禁止直接依赖 openai/litellm/docker/langchain/chromadb。
"""
