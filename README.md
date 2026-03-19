# DocSearch

面向 AI Agent 的文档检索与 RAG 增强系统，支持从大型文档库中精准、高效地获取相关内容。

## 功能特性

- **文档处理**：通过 Docling 将 PDF/DOCX 转换为结构化 Markdown，保留表格和格式
- **智能分块**：语义分割，保持段落完整性与表格结构
- **三种 Agent 技能**：
  - `query` — 语义 + 关键词混合 RAG 召回
  - `read` — 顺序文档阅读与上下文扩展
  - `grep` — 跨文档正则/关键词模式匹配
- **智能路由**：Agent 根据文档数量与大小自动选择最优检索策略
- **精准定位**：结果包含文档来源、页码、标题面包屑、元素类型及相关性得分

## 系统架构

```
DocSearch
├── backend/           # FastAPI 后端
│   └── src/
│       ├── ingestion/ # 文档 → 分块 → 向量化 Pipeline
│       ├── retrieval/ # 向量检索 / 关键词检索 / 混合检索 / 重排
│       ├── skills/    # Agent Tool 接口 (query / read / grep / routing)
│       └── api/       # REST API 端点
├── frontend/          # React 18 + Ant Design X 前端
├── docker/            # Docker Compose 基础设施
└── specs/             # 需求规格与实现计划
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python 3.11 · FastAPI |
| 数据库 | PostgreSQL 16 + pgvector + ParadeDB |
| 对象存储 | MinIO |
| 缓存 & 队列 | Redis · Celery |
| 嵌入模型 | BAAI/bge-m3 (中英双语, 1024 维) |
| 重排模型 | BAAI/bge-reranker-v2-m3 |
| 文档解析 | Docling |
| 前端 | React 18 · TypeScript · Ant Design 5 · Zustand |
| 混合检索融合 | RRF (Reciprocal Rank Fusion) |

## 快速开始

### 前置条件

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+

### 1. 克隆仓库

```bash
git clone https://github.com/zhaoxuanZzz/DocSearch.git
cd DocSearch
```

### 2. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，按需调整以下配置：

```env
# 数据库
DATABASE_URL=postgresql+psycopg://docsearch:docsearch@localhost:5432/docsearch

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Redis
REDIS_URL=redis://localhost:6379/0

# 嵌入模型 (支持中英文)
EMBEDDING_MODEL=BAAI/bge-m3
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

### 3. 启动基础设施

```bash
cd docker
docker compose up -d postgres redis minio
```

### 4. 初始化数据库

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
```

### 5. 启动后端服务

```bash
# API 服务
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Celery 异步 Worker（新终端）
celery -A src.ingestion.celery_app worker --loglevel=info
```

### 6. 启动前端

```bash
cd frontend
npm install
npm run dev     # 访问 http://localhost:5173
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/healthz` | 健康检查 |
| `POST` | `/api/v1/documents` | 上传文档 |
| `GET` | `/api/v1/documents` | 文档列表 |
| `POST` | `/api/v1/skills/query` | 混合语义搜索 |
| `POST` | `/api/v1/skills/read` | 顺序文档阅读 |
| `POST` | `/api/v1/skills/grep` | 正则模式匹配 |
| `POST` | `/api/v1/routing/suggest` | 检索策略推荐 |
| `GET` | `/api/v1/metrics` | 系统指标 |

### 示例：混合检索

```bash
curl -X POST http://localhost:8000/api/v1/skills/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "合同违约金条款",
    "top_k": 5,
    "document_ids": []
  }'
```

### 示例：策略路由

```bash
curl -X POST http://localhost:8000/api/v1/routing/suggest \
  -H "Content-Type: application/json" \
  -d '{
    "query": "第3章第2节的内容是什么",
    "document_ids": ["doc-uuid-1"]
  }'
```

## 性能指标

| 指标 | 目标值 |
|------|--------|
| Top-5 召回率 | ≥ 90% |
| p95 查询延迟 | ≤ 2 秒 |
| 支持分块规模 | 100K+ |
| 混合 vs 纯向量 MRR 提升 | ≥ 15% |

## 项目结构详解

```
backend/src/
├── api/
│   ├── documents.py      # 文档上传与管理
│   ├── skills.py         # query / read / grep 技能端点
│   ├── routing.py        # 策略路由端点
│   └── metrics.py        # 可观测性指标
├── ingestion/
│   ├── converter.py      # Docling PDF/DOCX → Markdown
│   ├── chunker.py        # 语义分块（保留表格）
│   ├── embedder.py       # sentence-transformers 向量化
│   └── pipeline.py       # Celery 异步编排
├── retrieval/
│   ├── vector_search.py  # pgvector HNSW 检索
│   ├── keyword_search.py # ParadeDB BM25 检索
│   ├── hybrid.py         # RRF 融合
│   ├── reranker.py       # cross-encoder 重排
│   └── context_expander.py # 上下文窗口扩展
├── skills/
│   ├── query_skill.py    # 混合 RAG 技能
│   ├── read_skill.py     # 顺序阅读技能
│   ├── grep_skill.py     # 正则匹配技能
│   └── routing_advisor.py # 路由决策
├── models/
│   ├── document.py       # Document ORM 模型
│   ├── chunk.py          # Chunk ORM 模型
│   └── schemas.py        # Pydantic 请求/响应模式
└── core/
    ├── config.py         # 应用配置（pydantic-settings）
    ├── db.py             # 数据库连接与会话
    └── middleware.py     # 请求 ID / 日志中间件
```

## 开发

### 运行测试

```bash
cd backend
pytest tests/unit/          # 单元测试
pytest tests/integration/   # 集成测试（需要运行中的基础设施）
```

### 代码格式化

```bash
ruff check src/ --fix
ruff format src/
```

## 许可证

MIT
