# 智能标准文档管理与 RAG 问答系统

> 基于 FastAPI + Vue 3 + DeepSeek 的企业标准文档智能问答平台。支持 PDF/DOCX/TXT 上传、结构感知切片、混合检索（关键词+语义）、SSE 流式问答、标准动态监控。

## 功能特性

- 📄 **文档管理** — 上传/下载/搜索/筛选 PDF、DOCX、TXT 标准文件
- 🧩 **智能切片** — v2 结构感知切片，按封面/前言/范围/术语/条款/表格/附录区域精准切分
- 🔍 **混合检索** — jieba 关键词 + sentence-transformers 语义检索 + 联动父子 chunk 扩展
- 💬 **流式问答** — SSE 逐 token 推送，DeepSeek 生成，强制条款引用+原文摘录
- 📖 **相关推荐** — 同行业/语义相似/引用关系三维度推荐相关标准
- 🔎 **标准监控** — 标准版本追踪、状态变更日志、自动/手动检查

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy + MySQL |
| 前端 | Vue 3 + Element Plus + ECharts |
| AI | DeepSeek + sentence-transformers (MiniLM) |
| OCR | PaddleOCR + PyMuPDF |
| 分词 | jieba |

## 快速开始

### 1. 环境要求

- Python 3.10+
- MySQL 8.0+
- Node.js 18+

### 2. 后端部署

```bash
# 克隆仓库
git clone https://github.com/yourname/standard-ai.git
cd standard-ai

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env_example .env
# 编辑 .env，填入你的 DeepSeek API Key

# 初始化数据库（在 MySQL 中创建 standard_ai 库后）
python init_db.py
python migrate_chunks_v2.py
python migrate_v3_watchdog_ocr.py

# 启动后端
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 前端部署

```bash
cd standard_ai_frontend
npm install
npm run dev
```

访问 `http://localhost:5173`

### 4. 数据库配置

默认连接: `mysql+pymysql://root:123456@127.0.0.1:3306/standard_ai`

可在 `database.py` 中修改。

## API 接口概览

| 接口 | 说明 |
|------|------|
| `POST /documents/upload` | 上传标准文件（自动切片+注册监控） |
| `GET /documents` | 文档列表（筛选+分页） |
| `POST /ask` | RAG 问答（混合检索+LLM） |
| `POST /ask/stream` | SSE 流式问答 |
| `GET /documents/stats` | 统计信息 |
| `GET /standards/watchdog` | 标准状态监控 |
| `POST /standards/watchdog/backfill-all` | 一键回填已有文档 |

## 项目结构

```
standard_ai/
├── main.py                 # FastAPI 入口
├── models.py               # SQLAlchemy 数据模型
├── schemas.py              # Pydantic 请求/响应模型
├── database.py             # 数据库连接配置
├── requirements.txt        # Python 依赖
├── routers/
│   ├── documents.py        # 文档管理+问答接口
│   └── watchdog.py         # 标准监控接口
├── services/
│   ├── document_service.py # 文档解析/切片/检索
│   ├── llm_service.py      # DeepSeek 调用
│   ├── embedding_service.py# 向量化服务
│   ├── anaylysis_service.py# 文档分析
│   └── watchdog_service.py # 标准监控服务
├── standard_ai_frontend/   # Vue 3 前端
│   └── src/
│       ├── App.vue         # 主组件
│       └── services/api.js # API 封装
└── uploads/                # 上传文件存储（gitignore）
```

## License

MIT
