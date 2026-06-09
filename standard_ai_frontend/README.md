# standard_ai_frontend

智能标准文档管理与 RAG 问答系统前端最小可用版。

## 技术栈

- Vue 3
- Vite
- Element Plus
- Axios

## 已包含功能

- 标准文档上传
- 文档列表展示
- 文档切片 / Embedding 生成
- 智能问答
- answer 展示
- references 来源展示，包括 filename、chunk_index、match_type、score、content_preview

## 启动方式

```bash
npm install
npm run dev
```

浏览器打开终端提示的地址，一般是：

```text
http://127.0.0.1:5173
```

## 后端地址配置

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

Windows 可以手动复制并改名。

默认后端地址：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 依赖的后端接口

默认使用以下接口：

```text
GET  /documents
POST /documents/upload
POST /documents/{document_id}/chunks
POST /ask
```

如果你的后端接口路径不同，请修改：

```text
src/services/api.js
```

## FastAPI CORS 提醒

如果浏览器请求后端时报 CORS 错误，在 FastAPI `main.py` 里添加：

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

开发阶段可以先用 `allow_origins=["*"]`，正式环境再限制域名。
