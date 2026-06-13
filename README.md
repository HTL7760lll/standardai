# 智能标准文档管理与 RAG 问答系统

> 面向标准工程师和研究人员的 AI 助手。上传标准文档（PDF/DOCX/TXT），智能解析切片，自然语言问答，多标准对比分析。

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 功能演示

```
上传标准 → 自动解析切片 → 问答/对比/起草辅助

📄 文档管理    — 上传/搜索/筛选/删除，支持扫描件 OCR
🔍 智能问答    — 自然语言提问，条款级精确引用（含章节路径+页码）
📊 多标准对比  — 同时查 2-5 份标准，自动生成对比表格+异同分析
📝 起草辅助    — 上传草案，逐条检查是否与现行标准冲突
🔗 引用图谱    — 可视化标准间的引用关系网络
👤 三级权限    — 管理员/工程师/访客，角色分离
✏️ 标注笔记    — 条款级私有笔记
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + SQLAlchemy + MySQL |
| 前端 | Vue 3 + Element Plus + ECharts |
| LLM | DeepSeek Chat API |
| 向量模型 | sentence-transformers (MiniLM-L12, 384维) |
| OCR | PaddleOCR 2.7 + PyMuPDF |
| 分词 | jieba |
| 向量加速 | faiss IndexFlatIP |
| 全文索引 | MySQL FULLTEXT ngram |
| 认证 | JWT + bcrypt |
| 日志 | structlog + RotatingFileHandler |

## 快速启动

### 环境要求

- Python 3.10+
- MySQL 8.0+
- Node.js 18+

### 1. 后端

```bash
git clone https://github.com/HTL7760lll/standardai.git
cd standard_ai

# 虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 依赖
pip install -r requirements.txt

# 配置 .env（填入 DeepSeek API Key）
cp .env_example .env

# 创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS standard_ai DEFAULT CHARSET utf8mb4"

# 启动（首次运行自动建表+构建faiss索引）
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. 前端

```bash
cd standard_ai_frontend
npm install
npm run dev
```

访问 `http://localhost:5173`

### 3. Docker（一键部署）

```bash
docker-compose up -d
```

含 API + MySQL + Nginx 三服务。

## 项目结构

```
standard_ai/
├── main.py                      # FastAPI 入口
├── config.py                    # 统一配置（.env 读取）
├── database.py                  # 数据库连接
├── models.py                    # ORM 模型（6 张表）
├── schemas.py                   # Pydantic 模型
├── logging_config.py            # 结构化日志
├── routers/
│   ├── documents.py             # 文档+问答+对比+起草
│   ├── auth.py                  # JWT 登录/注册/权限
│   └── annotations.py           # 用户标注笔记
├── services/
│   ├── document_service.py      # 解析/切片/检索/提取
│   ├── llm_service.py           # DeepSeek 调用
│   ├── embedding_service.py     # 向量化
│   ├── auth_service.py          # 密码哈希+JWT
│   ├── vector_index.py          # faiss 索引
│   └── cache.py                 # 内存缓存
├── standard_ai_frontend/        # Vue 3 前端
├── uploads/                     # 上传文件
├── logs/                        # 日志文件
├── Dockerfile
└── docker-compose.yml
```

## API 接口

| 接口 | 说明 | 权限 |
|------|------|:--:|
| `POST /auth/register` | 注册 | 无 |
| `POST /auth/login` | 登录 | 无 |
| `POST /documents/upload` | 上传文件 | 管理员/工程师 |
| `GET /documents` | 文档列表 | 所有角色 |
| `POST /documents/{id}/chunks` | 生成切片 | 管理员/工程师 |
| `POST /documents/{id}/analyze` | AI 分析 | 管理员/工程师 |
| `DELETE /documents/{id}` | 删除文档 | 管理员/工程师 |
| `POST /ask` | 问答 | 所有角色 |
| `POST /ask/stream` | 流式问答 | 所有角色 |
| `GET /documents/{id}/clauses` | 条款列表 | 所有角色 |
| `POST /documents/{id}/draft-check` | 起草辅助 | 所有角色 |
| `GET /documents/citations/graph` | 引用图谱 | 所有角色 |
| `POST /annotations` | 添加标注 | 所有角色 |
| `GET /health` | 健康检查 | 无 |

## License

MIT
