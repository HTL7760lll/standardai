# 开发日志
## 2026-06-01
### 已完成的功能
- 实现标准文件上传接口，支持 txt、pdf、docx 文件上传。
- 实现文件本地保存，并将 filename、filepath、standard_type、industry、tags 等信息写入 documents 表。
- 实现文档下载接口，支持通过 document_id 下载对应文件。
- 实现文档解析功能，支持 txt、pdf、docx 内容读取。
- 实现文本切片功能，将文档内容切分为 chunks。
- 设计 document_chunks 表，保存 document_id、chunk_index、content、created_at。
- 实现重复切片清理机制，重新生成 chunks 前先删除旧 chunks。
- 实现关键词搜索接口，可根据 keyword 查询相关 chunk。
- 实现 /qa/search 上下文检索接口。
- 实现 /ask 问答接口，支持 references、prompt_preview 返回。
- 接入 DeepSeek，实现基于检索内容的回答生成。

### 已修复的问题：
- 修复上传文件成功但数据库入库失败时文件残留的问题。
- 修复 filepath 为空导致下载失败的问题。

### 当前问题
- PDF 解析部分文件会出现乱码。
- 当前检索仍基于 contains，只能查询关键词，无法很好处理自然语言问题。
- 暂未实现向量检索和 Embedding。

### 下一步计划
- 解决PDF解析部分文件会出现乱码的问题，PDF的文字可能是扫描图片导致的，而我用的是提取文本层extract_text()，后续要接入OCR
- 接入向量检索和 Embedding，替换掉contains进行文件查询和反馈，也就是def extract_keyword函数。
- 解决输入长句子进行分词的方法，通过多关键词进行检索，提升长句子的召回能力。


### 2026-06-02
### 已修复的问题
- 在 `parse_document()` 中增加 `.docx` `.pdf` 复杂结构判断：当文档包含普通表格时主动抛出 `ValueError`，当普通段落解析结果为空时提示可能包含文本框、图片文字或复杂排版。
- 在 router 层通过 `try...except ValueError` 捕获业务异常，并统一转换为 `HTTPException(status_code=400)` 返回给前端，避免接口直接返回 500 或模糊的空文本提示。
- 实现了向量检索和Embedding功能，Deepseek在回复时能依据匹配值进行返回。

### 当前限制
- 当前 `.docx` `.pdf` 只能解析主要支持普通正文段落。后续可通过解析 docx 底层 XML、转换为 HTML/PDF 或接入 OCR 的方式增强复杂文档解析能力。对于表格、文本框、形状对象、图片文字等复杂排版内容，暂时不进行拆解解析，仅返回明确提示。
- 发现纯 Embedding 语义检索在人名、标准编号、文件名等精确实体查询场景下召回不稳定，后续计划增加 Hybrid Search，将关键词检索与语义检索结合，提高专有名词和自然语言问题的整体召回效果。

### 优化记录
- 优化文档解析异常处理逻辑，将“解析结果为空”进一步细分为“文件无文本内容”和“文档包含复杂排版暂不支持”两类场景，提高接口返回信息的可读性和可维护性。

### 2026-06-03
### 已完成功能
- 新增 `document_analysis` 表，用于保存标准文档自动分析结果。
- 新增 `/documents/{document_id}/analyze` 接口，支持基于文档 chunks 调用 DeepSeek 生成标准类型、行业分类、摘要、关键词和适用范围。
- 完成分析结果入库与接口返回，初步实现标准文档自动解读能力。
- 新增 Hybrid Search，能将关键词检索和语义检索想结合
- 接入前端页面，模拟真实的用户体验。

### 当前问题
- 行业分类目前依赖模型自由判断，分类粒度不够统一。
- 当前分析仅基于前几个 chunks，可能无法覆盖完整标准内容。
- 适用范围字段在资料不充分时容易返回“资料中未明确说明”。

### 2026-06-04
### 已完成的功能
- 在ask接口处新增根据id搜索检索范围进行关键词和语义搜索
- 优化掉废弃掉重复的qa接口
- 新增analysis接口，能通过原先给定的提示词对用户上传的文件进行关键信息的筛选，
- 与ask不同的是格式相对固定，一般只提取标准类型、行业、摘要、关键词、适用范围。
- 在 `AskQuestion` 中增加 `document_id` 可选字段，让关键词检索、语义检索和混合检索都支持 `document_id` 过滤
- 实现用户针对“刚刚上传的某份标准”进行适用性判断和内容问答。
### 当前限制

- pdf乱码仍未解决，上传pdf或word文档存在表格或者特殊字符的时候会出现报错。
- 切分关键词仍存在不足，对于标点符号和文字分段还不够足。

### 下一步优化
- pdf的乱码现象可能是扫描件出现的问题，通过OCR，识别文档中的文字转化成文本text。

### 2026-06-05
#### 已完成的功能
- **PDF OCR**：新增 `_ocr_pdf_with_paddle()`，PaddleOCR + PyMuPDF 对扫描件 PDF 逐页 OCR，先 pypdf 提取 → 乱码检测 → 自动降级 OCR。PaddleOCR/PyMuPDF 懒加载
- **Word 表格/文本框提取**：新增 `_extract_docx_tables()` 和 `_extract_docx_textboxes()`，删除原先遇表格抛异常的拦截。DOCX 解析 = 段落 + 表格 + 文本框
- **智能切片**：新增 `smart_split_text()`，优先在条款编号/段落/句子边界切割，替代原固定长度 `split_text()`
- **jieba 分词**：新增 `_jieba_extract_keywords()` 用 jieba posseg 词性标注提取关键词，`_extract_clause_refs()` 提取条款引用，整合为 `extract_search_terms()`
- **条款级检索**：`/ask` prompt 优化，要求引用条款编号；`extract_search_terms()` 自动保留条款模式
- **前端重设计**：双视图导航（问答/文档库），AI左用户右聊天气泡，引用来源移出气泡；文档库含统计卡片+ECharts饼图+筛选+分页；上传自动切片；分析对话框标准编号从文件名正则提取；饼图 dispose-and-recreate 防消失；国家标准公开系统外链
- **分析接口优化**：`get_analysis_context()` 始终含前3个chunk，内容预览扩至1500字符，prompt 增加标准名称/编号提取指引，移除 confidence/missing_info

#### 已修复的问题
- CORS 跨域：`main.py` 添加 `CORSMiddleware`
- 422 错误：`AskQuestion.document_id` 加默认值 `None`
- DELETE 500：修复 `document.d_document` 错误属性，级联删除 chunks/analysis/磁盘文件
- `requirements. txt` 文件名空格修复
- `embedding_service.py` 加载失败 try/except 友好提示
- 多处中文引号 `""` 混入 Python 字符串导致 SyntaxError
- 饼图切换消失：dispose 旧实例 + watch 触发重绘
- 端口占用：kill 残留 uvicorn 进程
- npm 路径：Node.js 在 `E:\Node` 未入 PATH

#### 新增依赖
- `paddlepaddle`、`paddleocr`、`PyMuPDF`、`jieba`

### 2026-06-08
#### 已完成的功能
- **v2 结构感知切片**：新增 `smart_split_v2()` 替代 v1 简单切片，按文档区域类型精准切分：
  - 封面 → 1 chunk（含标准编号/名称）
  - 前言 → 1-2 chunk（超1200字按段落拆）
  - 范围 → 1 chunk
  - 规范性引用文件 → 1 chunk（或按引用标准分条）
  - 术语和定义 → 每条术语独立或按500字合并
  - 正文条款 → 按条款号切分（300-500字基准），短条款合并、长条款自然段拆分，保留父级路径
  - 表格 → 整表1 chunk，不拆行
  - 图/公式 → 图题+上下文1 chunk
  - 附录 → 按附录内条款切分
- **文档结构解析引擎**：新增 `parse_document_structure()` + `_detect_major_sections()` + `_parse_clause_tree()` + `_flatten_clauses()`，自动识别封面/前言/范围/引用/术语/正文/附录区域边界，构建条款层级树
- **Chunk 内容前缀**：入库时自动拼接 `标准：{名称}（{编号}）\n章节路径：{path}\n页码：第X页` 前缀，检索命中后用户和大模型可直观看到来源
- **父子层级关系**：`_assign_parent_refs()` 根据条款编号建立父子引用，存入 `parent_chunk_id` 和 `chunk_relations` 表
- **联动检索**：新增 `expand_search_results()`，命中 chunk 时自动连带返回父级 chunk 和子级 chunk（depth=1）

#### 数据库变更
- `document_chunks` 新增 5 列：`chunk_type`、`section_path`、`section_number`、`parent_chunk_id`、`page_number`
- 新增 `chunk_relations` 表（chunk_id, related_chunk_id, relation_type）
- 迁移脚本：`migrate_chunks_v2.py`

#### 接口变更
- `/documents/{id}/chunks` 改用 `smart_split_v2()`，返回增加 `chunk_types` 统计
- `/ask` 增加联动检索 `expand_search_results`，references 新增 `chunk_type`、`section_path` 字段
- `save_document_chunk()` 兼容 v1 (str) 和 v2 (dict) 两种格式

#### 当前限制
- 页码依赖 PDF 解析的页面标记，DOCX/TXT 无页码
- TOC（目录）行通过省略号过滤，但对无省略号的 TOC 仍可能误识别
- 表格检测依赖解析阶段的 `[表格 N]` 标记，对 Markdown 原生的表格支持有限