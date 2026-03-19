# Implementation Plan: Agent 文档检索与 RAG 增强系统

**Branch**: `001-agent-doc-rag-retrieval` | **Date**: 2026-03-17 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/001-agent-doc-rag-retrieval/spec.md`

## Summary

构建一套面向 AI Agent 的文档检索与知识召回系统。核心能力：通过 Docling 将 PDF/DOCX 结构化转换为带位置元数据的 Markdown，然后进行语义分块与向量化索引；为 Agent 提供三种文档技能（`query` 混合召回、`read` 顺序阅读、`grep` 模式匹配），以及基于文档集规模的策略路由建议。技术栈为 Python + DeepAgents（后端）、React + Ant Design X（前端）、PostgreSQL + pgvector（数据 & 向量）、MinIO（对象存储）、Redis（缓存）。

## Technical Context

**Language/Version**: Python 3.11（后端服务）；TypeScript / Node.js 20（前端）  
**Primary Dependencies**: DeepAgents, Docling, pgvector, FastAPI（或 DeepAgents 内置路由）, Celery + Redis（异步任务），MinIO Python SDK, psycopg3, sentence-transformers（或兼容 API）, cross-encoder（reranker）  
**Storage**: PostgreSQL 16 + pgvector（文档元数据 + Chunk 元数据 + 向量存储）；MinIO（原始文件 + Docling Markdown）；Redis（查询缓存 / 索引状态 / 路由建议缓存）  
**Testing**: pytest + pytest-asyncio（后端）；Vitest + React Testing Library（前端）；Locust（性能测试）  
**Target Platform**: Linux 服务器（私有部署，Docker Compose / Kubernetes）  
**Project Type**: Web Service（后端 REST/WebSocket API + 前端管理界面 + Agent Tool 层）  
**Performance Goals**: p95 查询 ≤ 2s；文档索引 ≤ 5 min（100MB）；50 QPS 时响应增幅 ≤ 20%  
**Constraints**: 所有文档处理在私有环境完成，不调用外部 LLM API；单文档 ≤ 200MB  
**Scale/Scope**: 10 万 Chunk 向量规模；支持 50 并发 Agent 查询

## Constitution Check

*GATE: 无 constitution.md 文件（尚未创建项目宪法），跳过规则检查，以最小复杂度原则评估。*

| 检查项 | 评估 | 说明 |
|--------|------|------|
| 项目结构是否最小够用 | ✅ | 前后端分离是技术栈要求，非过度工程 |
| 是否引入不必要抽象 | ✅ | 三种技能直接映射 FR-019~021，无多余层 |
| 存储选型是否合理 | ✅ | PostgreSQL 统一关系 + 向量，减少多组件复杂度 |
| 异步任务是否必要 | ✅ | 文档解析（Docling）耗时无法同步，Celery 必要 |

**Gate 结论**: 通过，可进入 Phase 0 研究。

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-doc-rag-retrieval/
├── plan.md              ← 本文件
├── research.md          ← Phase 0 输出
├── data-model.md        ← Phase 1 输出
├── quickstart.md        ← Phase 1 输出
├── contracts/           ← Phase 1 输出
│   ├── query-skill.md
│   ├── read-skill.md
│   ├── grep-skill.md
│   └── routing-advisor.md
└── tasks.md             ← Phase 2 输出（/speckit.tasks 命令生成）
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml
├── alembic/                        # 数据库迁移
├── src/
│   ├── core/
│   │   ├── config.py               # 配置（env-based）
│   │   └── db.py                   # PostgreSQL 连接池
│   ├── ingestion/
│   │   ├── converter.py            # Docling PDF/DOCX → Markdown
│   │   ├── chunker.py              # Markdown 语义分块（含表格策略）
│   │   ├── embedder.py             # 向量化（sentence-transformers）
│   │   └── pipeline.py             # 摄入异步流水线（Celery task）
│   ├── retrieval/
│   │   ├── vector_search.py        # pgvector 语义检索
│   │   ├── keyword_search.py       # PostgreSQL FTS / BM25
│   │   ├── hybrid.py               # RRF 融合
│   │   ├── reranker.py             # cross-encoder 重排序
│   │   └── context_expander.py     # 上下文窗口扩展
│   ├── skills/
│   │   ├── query_skill.py          # query 技能（DeepAgents Tool）
│   │   ├── read_skill.py           # read 技能（DeepAgents Tool）
│   │   ├── grep_skill.py           # grep 技能（DeepAgents Tool）
│   │   └── routing_advisor.py      # 路由建议服务
│   ├── storage/
│   │   ├── minio_client.py         # MinIO 对象存储
│   │   └── cache.py                # Redis 缓存
│   ├── api/
│   │   ├── documents.py            # 文档管理端点
│   │   ├── skills.py               # Agent 技能端点（query/read/grep）
│   │   └── routing.py              # 路由建议端点
│   └── models/
│       ├── document.py             # SQLAlchemy ORM 模型
│       ├── chunk.py
│       └── schemas.py              # Pydantic 请求/响应模型
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/

frontend/
├── package.json
├── src/
│   ├── pages/
│   │   ├── DocumentLibrary/        # 文档库管理页
│   │   ├── ChatWorkspace/          # Agent 对话主界面
│   │   └── Settings/               # 系统配置页
│   ├── components/
│   │   ├── DocumentUploader/
│   │   ├── ChunkViewer/            # 检索结果 + 精准位置高亮
│   │   ├── AgentChat/              # Ant Design X 对话组件
│   │   └── StrategyBadge/          # 策略路由可观测性标签
│   ├── services/
│   │   ├── documentApi.ts
│   │   └── skillsApi.ts
│   └── stores/
│       └── documentStore.ts
└── tests/

docker/
├── docker-compose.yml              # 本地开发一键启动
└── docker-compose.prod.yml
```

**Structure Decision**: 前后端分离（技术栈要求），后端按职责分层（ingestion / retrieval / skills / api），技能层（skills/）直接映射 DeepAgents Tool 接口，与检索层解耦。

## Complexity Tracking

*无 Constitution 违规项，不适用。*
