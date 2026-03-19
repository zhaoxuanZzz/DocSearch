---
description: "Task list for Agent 文档检索与 RAG 增强系统"
---

# Tasks: Agent 文档检索与 RAG 增强系统

**Input**: Design documents from `/specs/001-agent-doc-rag-retrieval/`
**Branch**: `001-agent-doc-rag-retrieval`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅
**Tests**: 未在 spec 中明确要求 TDD，测试任务列于最终 Polish 阶段

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（不同文件，无未完成任务依赖）
- **[Story]**: 所属用户故事（US1–US6）
- 所有路径基于 plan.md 中定义的项目结构

---

## Phase 1: Setup（项目初始化）

**Purpose**: 建立基础项目骨架与开发环境配置

- [X] T001 创建项目目录结构：`backend/`、`frontend/`、`docker/` 按 plan.md 目录树初始化
- [X] T002 [P] 初始化后端项目：`backend/pyproject.toml`（Python 3.11，依赖：deepagents、docling、pgvector、psycopg3、celery、redis、minio、sentence-transformers、fastapi、langchain、pydantic）
- [X] T003 [P] 初始化前端项目：`frontend/package.json`（React 18、TypeScript、Ant Design X、Vite）
- [X] T004 [P] 创建本地开发 `docker/docker-compose.yml`（PostgreSQL 16 + pgvector + pg_search、MinIO、Redis、Celery worker）
- [X] T005 [P] 配置后端代码规范：`backend/.ruff.toml`（linting）、`backend/.pre-commit-config.yaml`
- [X] T006 [P] 创建环境配置模板 `backend/.env.example`（DATABASE_URL、MINIO_*、REDIS_URL、EMBEDDING_MODEL、RERANKER_MODEL 等变量）

**Checkpoint**: `docker compose up` 可正常启动所有基础服务

---

## Phase 2: Foundational（基础公共设施）

**Purpose**: 所有用户故事的共同前置依赖，MUST 在任意故事开始前完成
**⚠️ CRITICAL**: 本阶段完成前，任何用户故事实现均无法开始

- [X] T007 实现核心配置模块 `backend/src/core/config.py`（Pydantic `BaseSettings`，从 env 读取所有配置项，含路由阈值 `SMALL_DOC_THRESHOLD`、`SMALL_SIZE_MB`、`GREP_DOC_LIMIT`）
- [X] T008 实现数据库连接池 `backend/src/core/db.py`（psycopg3 async 连接池，连接 PostgreSQL，暴露 `get_db()` 依赖注入）
- [X] T009 创建数据库迁移框架：`backend/alembic/`（alembic init，配置 `alembic.ini` 指向 PostgreSQL）
- [X] T010 [P] 创建 `documents` 表迁移 `backend/alembic/versions/001_create_documents.py`（含所有字段、索引、状态枚举，按 data-model.md）
- [X] T011 [P] 创建 `chunks` 表迁移 `backend/alembic/versions/002_create_chunks.py`（含 `embedding vector(1024)`、所有位置元数据字段、HNSW 索引 m=16 ef_construction=64、BM25 索引）
- [X] T012 实现 ORM 模型 `backend/src/models/document.py`（SQLAlchemy `Document` 模型映射 `documents` 表，含状态常量 `PENDING/PROCESSING/INDEXED/FAILED`）
- [X] T013 [P] 实现 ORM 模型 `backend/src/models/chunk.py`（SQLAlchemy `Chunk` 模型映射 `chunks` 表，含 pgvector `VECTOR` 列类型）
- [X] T014 [P] 实现 Pydantic Schema `backend/src/models/schemas.py`（`DocumentCreate`、`DocumentResponse`、`ChunkPosition`、`ChunkResult`、`QueryInput`、`QueryOutput`）
- [X] T015 实现 MinIO 客户端 `backend/src/storage/minio_client.py`（上传原始文件到 `originals/{doc_id}/{file_name}`、上传 Markdown 到 `markdown/{doc_id}/converted.md`、下载、删除、presigned URL）
- [X] T016 [P] 实现 Redis 缓存工具 `backend/src/storage/cache.py`（`get/set/delete`，支持 TTL，序列化为 JSON，key 前缀对应 data-model.md 中的 5 种 key pattern）
- [X] T017 实现全局错误处理与日志中间件 `backend/src/core/middleware.py`（请求 ID 注入、结构化 JSON 日志、统一错误响应格式）
- [X] T018 [P] 创建 FastAPI 应用入口 `backend/src/main.py`（注册所有路由、中间件、lifespan 事件，DeepAgents/LangServe 集成骨架）
- [X] T019 [P] 配置 Celery 应用 `backend/src/ingestion/celery_app.py`（连接 Redis broker，定义 `app` 实例，worker 启动配置）

**Checkpoint**: `alembic upgrade head` 成功建表，FastAPI 服务 `/healthz` 返回 200

---

## Phase 3: User Story 5 — Agent 三模式文档技能 query/read/grep（Priority: P1）🎯 MVP

**Goal**: 为 Agent 提供三种文档访问技能（query/read/grep），使 Agent 能对已索引文档执行语义检索、顺序阅读和模式匹配。本阶段完成后系统具备核心 Agent 接口。

**Independent Test**: 手动上传一份已索引的文档（可 mock 跳过摄入流水线，直接写入 chunks 表），分别调用三个技能端点，验证返回格式符合 contracts/ 定义。

### Implementation for User Story 5

- [x] T020 [P] [US5] 实现向量检索模块 `backend/src/retrieval/vector_search.py`（pgvector HNSW 余弦相似度检索，支持 `doc_ids` 过滤，返回 Top-N 候选 + `chunk_index`，`hnsw.ef_search=100`）
- [x] T021 [P] [US5] 实现 BM25 关键词检索模块 `backend/src/retrieval/keyword_search.py`（ParadeDB `pg_search` BM25，`content @@@ $query` 语法，支持 `doc_ids` 过滤，返回 Top-N 候选）
- [x] T022 [US5] 实现 RRF 混合融合模块 `backend/src/retrieval/hybrid.py`（SQL WITH CTE 模式，k=60，FULL OUTER JOIN 合并向量排名与 BM25 排名，按 data-model.md 中 RRF 公式计算 score）
- [x] T023 [US5] 实现 Cross-encoder 重排序模块 `backend/src/retrieval/reranker.py`（加载 `bge-reranker-v2-m3`，Top-20 候选 → Top-K，score 归一化到 0-1）
- [x] T024 [P] [US5] 实现上下文扩展模块 `backend/src/retrieval/context_expander.py`（按 `chunk_index ± 1` 查询前后相邻 Chunk，`expand_context=true` 时触发）
- [x] T025 [US5] 实现 `query` 技能工具 `backend/src/skills/query_skill.py`（LangChain `@tool(args_schema=QueryInput)`，调用 hybrid.py + reranker.py + context_expander.py，Redis 缓存 key=`query:{hash}:{doc_ids_hash}:{mode}` TTL 5min，按 contracts/query-skill.md 返回 `QueryOutput`）
- [x] T026 [US5] 实现 `read` 技能工具 `backend/src/skills/read_skill.py`（LangChain `@tool(args_schema=ReadInput)`，token 模式：累积 chunks 至 max_tokens；heading 模式：返回同 breadcrumb 前缀的所有 chunks；cursor = base64 编码的 `{"chunk_index": N}`，按 contracts/read-skill.md 返回 `ReadOutput`）
- [x] T027 [US5] 实现 `grep` 技能工具 `backend/src/skills/grep_skill.py`（LangChain `@tool(args_schema=GrepInput)`，读取 MinIO Markdown 全文执行 Python `re` 匹配，`doc_ids` 总数 > `GREP_DOC_LIMIT` 时返回 `DOC_LIMIT_EXCEEDED`，按 contracts/grep-skill.md 返回 `GrepOutput`）
- [x] T028 [US5] 实现技能 API 端点 `backend/src/api/skills.py`（`POST /api/v1/skills/query`、`POST /api/v1/skills/read`、`POST /api/v1/skills/grep`，校验请求，调用对应技能工具，统一错误码映射）
- [x] T029 [US5] 将三个技能注册到 DeepAgents Agent `backend/src/agent.py`（`@tool` 列表注入，LangServe `add_routes(app, agent, path="/agent")`）

**Checkpoint**: `curl -X POST /api/v1/skills/query -d '{"query":"test","top_k":3}'` 返回格式正确的 `QueryOutput`；`/skills/read`、`/skills/grep` 同理

---

## Phase 4: User Story 1 — Agent 精准召回文档片段（Priority: P1）

**Goal**: 实现完整的混合召回链路（向量 + BM25 + RRF + rerank），使 query 技能在有真实文档数据时达成 SC-001（Top-5 召回率 ≥ 90%）、SC-002（MRR 提升 ≥ 15%）。

**Independent Test**: 向系统插入 golden dataset（10 条 Q&A 对的 chunks），调用 `query` 技能，验证 Top-5 结果中答案出现率 ≥ 90%。

### Implementation for User Story 1

- [x] T030 [US1] 实现嵌入模型服务 `backend/src/ingestion/embedder.py`（加载 `BAAI/bge-m3` sentence-transformers，`encode(texts, normalize=True)` → `vector(1024)`，支持批量，超长查询自动截断至 512 token）
- [x] T031 [US1] 补充 `query` 技能的 query 向量化调用链：`query_skill.py` 中调用 `embedder.py` 对 query 文本编码，然后传入 `vector_search.py`（T020 只实现了 SQL 层，此任务连接嵌入与检索）
- [x] T032 [US1] 在 `backend/src/api/skills.py` 的 query 端点补充完整错误处理：`QUERY_EMPTY`、`INVALID_MODE`、`NO_DOCS_FOUND`、`INDEX_NOT_READY`，对超长 query 设置 `query_truncated=true`
- [x] T033 [US1] 实现批量查询支持 `backend/src/api/skills.py`（`POST /api/v1/skills/query/batch`，接受 `queries: list[QueryInput]`，并发执行，返回 `list[QueryOutput]`，对应 FR-015）

**Checkpoint**: Golden dataset 测试通过，SC-001/SC-002 具备可验证基础

---

## Phase 5: User Story 4 — 多路召回融合与重排序（Priority: P2）

**Goal**: 使混合检索（向量 + BM25 + RRF + rerank）可配置、可调优，并提供独立的检索模式切换（`semantic` / `keyword` / `hybrid`），支持 SC-002 指标验证。

**Independent Test**: 对同一查询集分别以 `semantic`、`keyword`、`hybrid` 三种模式调用，验证 `hybrid` 的 MRR 相比 `semantic` 单独提升 ≥ 15%。

### Implementation for User Story 4

- [x] T034 [P] [US4] 补充 `vector_search.py` 中 `mode="semantic"` 的独立调用路径（绕过 BM25，直接返回 vector Top-K 结果，用于对比实验）
- [x] T035 [P] [US4] 补充 `keyword_search.py` 中 `mode="keyword"` 的独立调用路径（绕过向量检索，直接返回 BM25 Top-K 结果）
- [x] T036 [US4] 在 `hybrid.py` 中实现模式分发逻辑：根据 `mode` 字段决定走纯向量、纯 BM25 还是 RRF 融合路径
- [x] T037 [US4] 在 `reranker.py` 中添加 reranker 开关配置（`RERANKER_ENABLED` env var），允许在低延迟场景禁用；同时暴露 reranker 延迟指标写入响应的 `latency_ms` 字段
- [x] T038 [US4] 在 `query_skill.py` 中将 RRF k 参数、HNSW ef_search、reranker Top-N 暴露为 `core/config.py` 配置项，支持运行时调优

**Checkpoint**: 三种 mode 均可通过 API 独立调用，`hybrid` 相比 `semantic` MRR 具备提升

---

## Phase 6: User Story 2 — 长文档深度阅读与章节定位（Priority: P2）

**Goal**: `read` 技能支持真实长文档（100 页+）的章节定位与翻页阅读，位置元数据（heading_breadcrumb、page_no）可被 `read` 精准导航，SC-010 ≥ 98%。

**Independent Test**: 上传一份 100 页以上 PDF（需 Phase 7 摄入能力），对不同章节标题发起 `read` 请求，验证返回内容与预期章节对应，`next_cursor` 可正确翻页至文档末尾。

### Implementation for User Story 2

- [x] T039 [US2] 完善 `read_skill.py` 的 `start_breadcrumb` 前缀匹配逻辑（SQL：`heading_breadcrumb LIKE $prefix || '%'`，找到最小 `chunk_index` 作为起始位置）
- [x] T040 [US2] 完善 `read_skill.py` 的 `heading` 模式：从起始 Chunk 向后持续包含，直至遇到同级或父级标题块（通过比较 `heading_breadcrumb` 前缀深度判断边界）
- [x] T041 [US2] 实现 cursor 编解码工具函数（`encode_cursor(chunk_index: int) -> str`、`decode_cursor(cursor: str) -> int`，base64 JSON，无效 cursor 返回 `INVALID_CURSOR`）
- [x] T042 [P] [US2] 完善 `read` 端点的错误处理：`DOC_NOT_FOUND`、`POSITION_NOT_FOUND`（breadcrumb/page 无匹配时）、`DOC_NOT_INDEXED`、`INVALID_CURSOR`
- [x] T043 [US2] 在 `context_expander.py` 中实现 `expand_context` 功能用于 `read` 技能的上下文预扩展（FR-011：返回目标 Chunk 前后相邻内容），与 query 的 context 扩展复用同一函数

**Checkpoint**: 对真实长文档，`/skills/read` 可从任意章节起始翻页，`next_cursor` 链路完整直至 `is_end_of_document=true`

---

## Phase 7: User Story 3 — 文档库管理与增量更新（Priority: P3）

**Goal**: 管理员可上传 PDF/DOCX/MD/TXT 文档，系统自动完成 Docling 转换、分块、嵌入、索引全流水线，5 分钟内可被检索（SC-004）；支持文档更新与删除（SC-006）。

**Independent Test**: 上传一份 PDF，轮询状态接口，等待 status=indexed（≤5 分钟），然后调用 `query` 技能验证内容可被检索到；再删除文档，验证内容从检索结果消失。

### Implementation for User Story 3

- [x] T044 [US3] 实现 Docling 转换器 `backend/src/ingestion/converter.py`（`DoclingDocument.load(path)`，提取每个元素的 `prov.page_no`、`prov.bbox`、`label`、`parent` 链；调用 `build_breadcrumb()` 重建标题路径；对表格调用 `table.export_to_markdown()`；输出 Markdown 字符串 + 每段的位置元数据列表）
- [x] T045 [US3] 实现 Markdown 表格感知分块器 `backend/src/ingestion/chunker.py`（R4 算法：解析标题树 + 检测表格边界；小表（≤ 512 token）作为单 Chunk；大表按完整行分割 + 每子块保留表头行；non-table 块按语义边界滑动分块；每个 Chunk 携带完整位置元数据）
- [x] T046 [US3] 实现完整摄入 Celery 任务 `backend/src/ingestion/pipeline.py`（`ingest_document.delay(document_id)` task，依序执行：(1) 从 MinIO 下载原始文件 → (2) Docling 转换（PDF/DOCX）→ (3) 上传 Markdown 至 MinIO → (4) 分块 → (5) 批量嵌入 → (6) 批量写入 chunks 表 → (7) 更新 documents.status；每阶段更新 Redis `job:{task_id}` 进度）
- [x] T047 [US3] 实现文档管理 API 端点 `backend/src/api/documents.py`（`POST /api/v1/documents/upload`（multipart，写 MinIO + 创建数据库记录 + 触发 Celery 任务）、`GET /api/v1/documents/{id}/status`（返回 status + 进度）、`GET /api/v1/documents/`（列表 + 分页）、`DELETE /api/v1/documents/{id}`（级联删除 chunks + MinIO 文件 + 清除 Redis 缓存））
- [x] T048 [US3] 实现文档更新端点 `PUT /api/v1/documents/{id}` in `backend/src/api/documents.py`（上传新版本：MinIO 覆盖原始文件，status 重置为 `processing`，删除旧 chunks，重新触发 Celery 摄入任务）
- [x] T049 [US3] 实现文档库统计接口 `GET /api/v1/documents/stats` in `backend/src/api/documents.py`（返回已索引文档数、总 Chunk 数、各 status 的文档数，对应 FR-018）

**Checkpoint**: 上传 PDF → polling `status` 直至 `indexed` → `query` 技能可检索到文档内容；删除文档后内容消失

---

## Phase 8: User Story 6 — Agent 自主检索策略路由（Priority: P2）

**Goal**: 实现路由建议接口，Agent 调用后可获取推荐检索策略及依据，策略选择准确率达 SC-009（≥ 85%）；Agent 在响应中附带策略可观测性信息（FR-025）。

**Independent Test**: 构造两个场景：(A) 5 份文档 + `exact` 意图 → 期望推荐 `grep`；(B) 100 份文档 + `semantic` 意图 → 期望推荐 `query`。调用路由接口验证推荐结果和 confidence。

### Implementation for User Story 6

- [x] T050 [US6] 实现路由建议服务 `backend/src/skills/routing_advisor.py`（计算 `doc_count`、`total_size_bytes`；按 contracts/routing-advisor.md 中决策逻辑实现路由判断；Redis 缓存 `routing:{doc_count}:{total_size_kb}:{intent_hash}` TTL 1min）
- [x] T051 [US6] 实现路由建议 API 端点 `backend/src/api/routing.py`（`POST /api/v1/routing/suggest`，校验 `query_intent` 枚举，调用 `routing_advisor`，返回 `RoutingResponse`，按 contracts/routing-advisor.md）
- [x] T052 [US6] 在三个技能工具的响应中增加策略可观测性字段（`query_skill.py`、`read_skill.py`、`grep_skill.py` 的响应 metadata 中追加 `strategy_type` 和 `strategy_reason` 字段，对应 FR-025）
- [x] T053 [US6] 在 `routing_advisor.py` 中实现低置信度升级建议逻辑：当推荐 `query` 但查询意图为 `sequential` 时，`fallback_skill="read"`，附带 `low_confidence_note`（FR-024）

**Checkpoint**: 场景 A 和场景 B 均返回预期的 `recommended_skill`；三个技能的响应中均包含 `strategy_type` 字段

---

## Phase 9: 前端管理界面（Priority: P3）

**Goal**: 为管理员提供文档上传、状态查看和检索测试的 Web 界面，基于 React + Ant Design X 实现。

**Independent Test**: 浏览器打开管理界面，完成上传一份文档并等待 indexed 状态，然后在检索测试面板中输入查询并看到结果返回。

### Implementation for Phase 9：Frontend

- [x] T054 [P] 实现文档库管理页 `frontend/src/pages/DocumentLibrary/index.tsx`（文件上传组件 `DocumentUploader`：拖拽/选择上传，调用 `POST /api/v1/documents/upload`；文档列表：显示标题、状态（含进度轮询）、操作：删除/更新）
- [x] T055 [P] 实现检索测试面板 `frontend/src/pages/DocumentLibrary/SearchPanel.tsx`（输入框 + 模式选择（semantic/keyword/hybrid）+ top_k 滑块，调用 `/api/v1/skills/query`，结果列表显示文档来源 + `heading_breadcrumb` + 相关性分数）
- [x] T056 [P] 实现检索结果位置组件 `frontend/src/components/ChunkViewer/index.tsx`（展示每个 `ChunkResult` 的内容 + `page_no` + `heading_breadcrumb` + `element_type`，高亮显示路径；`StrategyBadge` 组件显示当前使用的策略）
- [x] T057 [P] 实现 API 服务层 `frontend/src/services/documentApi.ts` 和 `frontend/src/services/skillsApi.ts`（封装所有后端 API 调用，统一错误处理）
- [x] T058 [P] 实现系统配置页 `frontend/src/pages/Settings/index.tsx`（展示/编辑路由阈值 `SMALL_DOC_THRESHOLD`、`SMALL_SIZE_MB`、`GREP_DOC_LIMIT`，调用配置 API）

**Checkpoint**: 浏览器完整走通上传 → 索引 → 查询流程

---

## Phase 10: Polish & Cross-Cutting Concerns（收尾与横切关注点）

**Purpose**: 性能调优、测试覆盖、可观测性增强

- [x] T059 [P] 编写集成测试 `backend/tests/integration/test_query_skill.py`（golden dataset 10 条 Q&A，验证 Top-5 召回率、MRR，对应 SC-001/002）
- [x] T060 [P] 编写集成测试 `backend/tests/integration/test_ingestion_pipeline.py`（上传小 PDF，验证全流水线执行，status=indexed，Chunk 写入正确）
- [x] T061 [P] 编写集成测试 `backend/tests/integration/test_routing_advisor.py`（小文档集/大文档集场景，验证路由推荐准确率，对应 SC-009）
- [x] T062 [P] 实现 Prometheus 指标端点 `backend/src/api/metrics.py`（查询延迟 p95、摄入队列深度、缓存命中率，对应 SC-003/007）
- [x] T063 [P] 性能调优：在 `backend/src/core/db.py` 中配置 PostgreSQL 参数（`shared_buffers=4GB`、`work_mem=256MB`、HNSW `ef_search=100`），添加 connection pool size 配置（`pool_size=20`）
- [x] T064 运行 `quickstart.md` 完整验证流程（docker compose 启动 → 数据库迁移 → 上传测试文档 → 验证三种技能返回正确结果）

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
    └─► Phase 2 (Foundational)  ← BLOCKS all user stories
              ├─► Phase 3 (US5: query/read/grep 技能骨架) — P1，先做
              │       └─► Phase 4 (US1: 完整召回链路) — P1
              ├─► Phase 5 (US4: 多路融合调优) — P2，可与 Phase 6 并行
              ├─► Phase 6 (US2: 长文档阅读) — P2，可与 Phase 5 并行
              ├─► Phase 7 (US3: 摄入流水线) — P3，Phase 3 之后即可开始
              ├─► Phase 8 (US6: 路由建议) — P2，Phase 3 之后即可开始
              └─► Phase 9 (前端) — 可与 Phase 3-8 并行（只需 API 接口稳定即可）
Phase 10 (Polish) ← 所有期望完成的故事阶段完成后
```

### User Story Dependencies

| 故事 | 优先级 | 前置依赖 | 可并行的故事 |
|------|--------|----------|-------------|
| US5 (query/read/grep 技能) | P1 | Phase 2 | 无 |
| US1 (精准召回) | P1 | US5 + embedder | 无 |
| US4 (混合召回调优) | P2 | US5 Done | US2、US6、US3 |
| US2 (长文档阅读) | P2 | US5 Done | US4、US6、US3 |
| US6 (路由建议) | P2 | US5 Done | US4、US2、US3 |
| US3 (文档摄入) | P3 | Phase 2 | US4、US2、US6 |

### Parallel Opportunities per Story

**Phase 3 内部可并行（US5）**:
- T020 (`vector_search.py`) ‖ T021 (`keyword_search.py`) ‖ T024 (`context_expander.py`)

**Phase 5 内部可并行（US4）**:
- T034 (`vector_search` 独立模式) ‖ T035 (`keyword_search` 独立模式)

**Phase 7 内部可并行（US3）**:
- T044 (`converter.py`) ‖ T045 (`chunker.py`)（均不依赖对方）

**Phase 9 内部全部可并行（前端各页面相互独立）**:
- T054 ‖ T055 ‖ T056 ‖ T057 ‖ T058

---

## Implementation Strategy

### MVP Scope（建议第一个里程碑）

仅完成 **Phase 1 + Phase 2 + Phase 3**（T001–T029），即可交付：
- Agent 可通过 `query`、`read`、`grep` 三种技能访问文档库
- 检索内容携带精准位置元数据（`heading_breadcrumb` + `page_no`）
- 三个技能符合 contracts/ 定义的接口契约

**MVP 前提**：需手动向 `chunks` 表注入测试数据（跳过摄入流水线），或在 Phase 7 完成后再做完整端到端测试。

### Incremental Delivery Sequence

1. **Sprint 1**：Phase 1 + Phase 2（基础设施）
2. **Sprint 2**：Phase 3 + Phase 4（核心技能 + 召回链路，P1 故事完成）
3. **Sprint 3**：Phase 7（摄入流水线，使系统端到端可用）
4. **Sprint 4**：Phase 5 + Phase 6 + Phase 8（P2 故事，调优与路由）
5. **Sprint 5**：Phase 9 + Phase 10（前端 + 收尾）
