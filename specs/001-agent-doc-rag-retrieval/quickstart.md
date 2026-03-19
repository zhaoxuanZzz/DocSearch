# Quickstart: Agent 文档检索与 RAG 增强系统

**Branch**: `001-agent-doc-rag-retrieval` | **Date**: 2026-03-17

---

## 前置要求

| 工具 | 版本要求 | 用途 |
|------|----------|------|
| Docker + Docker Compose | 24+ | 一键启动所有服务 |
| Python | 3.11+ | 后端开发运行 |
| Node.js | 20+ | 前端开发运行 |
| uv（可选） | 最新 | Python 包管理加速 |

---

## 1. 克隆与初始化

```bash
git clone <repo-url> docsearch
cd docsearch
cp .env.example .env    # 后续步骤中编辑此文件
```

---

## 2. 配置环境变量

编辑 `.env`，填写以下必填项：

```dotenv
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=docsearch
POSTGRES_USER=docsearch
POSTGRES_PASSWORD=changeme

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=docsearch

# 嵌入模型（私有部署，不调用外部 API）
EMBEDDING_MODEL=BAAI/bge-m3      # 支持中英文混合
EMBEDDING_DIMENSION=1024
RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# DeepAgents / LLM
DEEPAGENTS_MODEL=<your-model-endpoint>

# 路由阈值（可选，修改默认值）
ROUTING_SMALL_DOC_THRESHOLD=5
ROUTING_SMALL_SIZE_MB=1.0
GREP_MAX_DOCS=20
```

---

## 3. 启动基础设施服务

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis minio
```

等待约 15 秒后验证服务就绪：

```bash
docker compose -f docker/docker-compose.yml ps
# 期望：postgres、redis、minio 均为 healthy
```

---

## 4. 初始化数据库

```bash
cd backend
pip install uv && uv sync        # 安装依赖
uv run alembic upgrade head      # 运行数据库迁移（建表 + pgvector + pg_search 扩展）
```

迁移脚本会自动创建：
- `documents` 表
- `chunks` 表（含 HNSW 向量索引 + BM25 索引）
- `indexing_jobs` 表

---

## 5. 启动后端服务

```bash
# 终端 1：API 服务
cd backend
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：Celery Worker（处理文档摄入异步任务）
cd backend
uv run celery -A src.celery_app worker --loglevel=info --concurrency=2
```

验证后端就绪：
```bash
curl http://localhost:8000/health
# 期望: {"status": "ok", "postgres": "connected", "redis": "connected", "minio": "connected"}
```

---

## 6. 启动前端服务

```bash
cd frontend
npm install
npm run dev
# 前端启动在 http://localhost:3000
```

---

## 7. 上传第一份文档

**通过前端界面**（推荐）：
1. 打开 

2. 进入「文档库管理」页
3. 点击「上传文档」，选择任意 PDF/DOCX/Markdown 文件
4. 等待状态从 `processing` 变为 `indexed`（约 1-3 分钟，取决于文档大小）

**通过 API**：
```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -F "file=@/path/to/your-doc.pdf" \
  -F "title=我的第一份文档"
# 返回: {"document_id": "1", "status": "pending"}

# 查询索引状态
curl http://localhost:8000/api/v1/documents/1/status
# 返回: {"status": "indexed", "chunk_count": 142}
```

---

## 8. 测试三种 Agent 技能

### query 技能
```bash
curl -X POST http://localhost:8000/api/v1/skills/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "如何配置数据库连接池？",
    "top_k": 3,
    "mode": "hybrid"
  }'
```

### read 技能
```bash
curl -X POST http://localhost:8000/api/v1/skills/read \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "1",
    "mode": "heading"
  }'
```

### grep 技能
```bash
curl -X POST http://localhost:8000/api/v1/skills/grep \
  -H "Content-Type: application/json" \
  -d '{
    "pattern": "API_KEY",
    "doc_ids": ["1"],
    "case_sensitive": false
  }'
```

### 路由建议
```bash
curl -X POST http://localhost:8000/api/v1/routing/suggest \
  -H "Content-Type: application/json" \
  -d '{
    "doc_ids": ["1"],
    "query_intent": "exact",
    "query_sample": "API_KEY 配置在哪里"
  }'
```

---

## 9. 运行测试

```bash
cd backend
uv run pytest tests/unit -v           # 单元测试
uv run pytest tests/integration -v    # 集成测试（需基础设施运行中）
```

---

## 服务端口一览

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:3000 | React 管理界面 |
| 后端 API | http://localhost:8000 | FastAPI / LangServe |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| MinIO 控制台 | http://localhost:9001 | 对象存储管理 |
| PostgreSQL | localhost:5432 | 数据库（用 `POSTGRES_*` 变量连接） |
| Redis | localhost:6379 | 缓存 |

---

## 常见问题

**Q: 文档状态一直停留在 `processing`？**  
A: 检查 Celery Worker 是否正常运行，查看 Worker 日志：`docker compose logs celery_worker`。如果是 PDF，Docling 转换可能需要较长时间（大型文档 1-5 分钟正常）。

**Q: 向量检索结果为空？**  
A: 确认 `EMBEDDING_MODEL` 路径正确，且模型已下载到本地（首次运行时会自动下载，需要网络访问 HuggingFace，或提前配置镜像源）。

**Q: BM25 索引报错 `extension "pg_search" not found`？**  
A: 运行 `docker compose up postgres` 确保使用带 ParadeDB 的 PostgreSQL 镜像（`image: paradedb/paradedb:latest`），而非标准 PostgreSQL 镜像。

**Q: grep 技能返回 `DOC_LIMIT_EXCEEDED`？**  
A: 缩小 `doc_ids` 列表，或将 `GREP_MAX_DOCS` 环境变量调高（注意：过高可能导致响应超时）。
