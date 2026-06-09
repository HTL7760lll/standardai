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

### 2026-06-09
#### 三大类问题根除：切片失败 + OCR 防乱码 + 召回重排准确度

#### 一、文档切片 Bug 修复

##### 已修复的问题：
- **`\b` 正则失效**：`_detect_major_sections()` 中 `范围\b`、`规范性引用文件\b` 等模式在中文后不匹配（Python `\b` 要求 `\w`↔`\W` 边界，中文是 `\W`）。已移除 `\b` 改为无边界匹配。
- **章节检测三层级联**：原只识别 GB/T 格式（1范围/2规范性引用文件/3术语和定义），对论文、报告等完全不适用。新增 Layer 1（GB/T 模式）→ Layer 2（通用标题：第X章、X.X 编号、一/二/三序号）→ Layer 3（短行+长段落启发式检测）。
- **Cover 截断守卫**：`_chunk_cover()` 原无条件截断到 500 字，章节检测失败时整篇文档被归入 cover 导致 95%+ 内容丢失。新增内容量守卫：cover content > 2000 字时自动回退到段落级切片。
- **兜底段落切片**：新增 `_chunk_fallback_paragraphs()` 函数，按空行切段、300-600 字合并。替代原「整篇塞进 1 个 chunk」的兜底逻辑。
- **最小切片保障**：`smart_split_v2()` 新增后置检查：文档 > 2000 字但产出 < 3 个 chunk → 强制触发段落切片。
- **Cover 误判保护**：`_detect_major_sections()` 中封面内容 > 3000 字 → 清空 sections 退化为全文 clauses，防止长文档被误判为封面。

##### 修改的文件：
- `services/document_service.py`：`_detect_major_sections()` 重写、`_chunk_cover()` 加守卫、新增 `_chunk_fallback_paragraphs()`、`smart_split_v2()` 增强兜底

#### 二、OCR 防乱码缺陷修复

##### 已修复的问题：
- **PaddleOCR 线程安全**：`_get_paddleocr()` 新增双重检查锁（double-checked locking），防止 4 个 OCR 工作线程同时初始化 PaddleOCR 导致 segfault。
- **OCR 主线程预加载**：`_ocr_pdf_with_paddle()` 在主线程中预初始化 PaddleOCR 引擎，避免工作线程竞态。
- **oneDNN 禁用**：模块级别设置 `os.environ["FLAGS_use_onednn"] = "0"`，在 PaddlePaddle import 前禁用 oneDNN 后端。
- **OCR 降级模式**：OCR 初始化失败或运行时崩溃时，标记 `_ocr_degraded = True`，后续调用自动跳过 OCR。不再抛 ValueError 阻塞上传流程，改为返回原始文本 + 警告前缀。
- **`_is_text_garbled()` 增强 v2**：
  - 有意义字符阈值从 20% 提升到 40%
  - 新增连续无效字符序列检测（>40 个连续乱码字符 → 判定乱码）
  - 新增伪 CJK 字符检测（CJK 扩展 B 区占比 >15% → 编码错误）
  - 新增纯数字表格豁免（digit_ratio > 30% → 不判乱码）
  - 新增合法标点白名单（中英文常见标点不计入乱码）
- **DOCX 嵌入图片 OCR**：新增 `_ocr_single_image()` 和 `_extract_docx_images()` 函数，从 DOCX XML 关系中提取嵌入图片并逐图 OCR，结果拼接到解析文本中。
- **DOCX 解析增强**：`parse_document()` DOCX 分支新增第 4 步提取嵌入图片 OCR，解析失败提示优化。

##### 已知限制：
- PaddlePaddle 3.3.1 的 PIR executor 与 PaddleOCR 存在底层不兼容（`Unimplemented: pir::ArrayAttribute<DoubleAttribute>`），`FLAGS_use_onednn=0` 无法完全绕过。扫描件 OCR 完全恢复需降级 PaddlePaddle 至 2.6.x 或换用 EasyOCR。

##### 修改的文件：
- `services/document_service.py`：模块级 oneDNN 禁用、`_get_paddleocr()` 双重检查锁、`_ocr_pdf_with_paddle()` 线程安全、`_ocr_single_image()` 新增、`_extract_docx_images()` 新增、`_is_text_garbled()` 重写、`parse_document()` PDF/DOCX 分支优化

#### 三、召回重排准确度修复

##### 已修复的问题：
- **IDF 加权**：新增 `_compute_idf_weights()` 函数，预计算所有 chunk 中词条的 IDF 值并缓存。高频通用词（如"标准"IDF=1.0）自动压制，低频专有词（如"消防安全"IDF=1.17）自动抬高。
- **多因子关键词评分**：关键词分数从单一 `0.55 + weight * 0.08` 改为 IDF 加权 + 匹配密度 + 位置加分 + 完整短语命中的多因子模型，分数范围 0.50~0.90，各 chunk 间有明确区分度。
- **RRF 融合**：混合检索从 `max()` 简单合并改为 Reciprocal Rank Fusion（k=60），关键词排名和语义排名交叉融合。
- **置信度分层**：`hybrid_search_chunks()` 返回 `(results, confidence)` 元组。confidence 分 high/medium/low/none 四层。low 级别不传 LLM，直接提示用户检索可信度低。
- **Embedding 模型升级**：`paraphrase-multilingual-MiniLM-L12-v2`（128 token）→ `BAAI/bge-large-zh-v1.5`（1024 token，中文专用，C-MTEB Top-3）。新增 `generate_query_embedding()` 函数，查询时自动添加 BGE instruction 前缀提升检索质量。新增 `normalize_embeddings=True` 确保余弦相似度计算准确。
- **零结果查询扩展**：`/ask` 和 `/ask/stream` 端点新增零结果重试机制，自动去掉疑问词（"请问""什么是""如何"等）后用简化查询重试。
- **低置信度拦截**：`/ask` 和 `/ask/stream` 端点新增 confidence==low 拦截，直接返回提示信息而非传 LLM。
- **retrieval_confidence 字段**：所有 `/ask` 和 `/ask/stream` 响应新增 `retrieval_confidence` 字段，前端可根据此字段展示检索质量指示器。

##### 修改的文件：
- `services/document_service.py`：新增 `_compute_idf_weights()`、`_expand_query_synonyms()`、重写 `hybrid_search_chunks()`（IDF+多因子+RRF+confidence）
- `services/embedding_service.py`：模型切换为 `BAAI/bge-large-zh-v1.5`、新增 `generate_query_embedding()`、`normalize_embeddings=True`
- `routers/documents.py`：`/ask` 和 `/ask/stream` 适配新 `(results, confidence)` 返回格式、新增零结果查询扩展、新增低置信度拦截、新增 `retrieval_confidence` 字段

#### 验证结果

| 测试项 | 修复前 | 修复后 |
|--------|--------|--------|
| 论文 PDF 切片覆盖 | 12 chunks, 21.6% | **60 chunks** |
| 大文档切片 | 1 chunk (186K字) | 段落级多chunk |
| 小文档切片 | 9 chunks | **18 chunks** |
| GB 标准切片 | 81 chunks | 81 chunks (保持) |
| 乱码检测精度 | 20%阈值，无连续检测 | 40%阈值+连续检测+CJK验证 |
| 关键词区分度 | 所有结果同分 | IDF加权+多因子，分数分散 |
| 检索置信度 | 无 | high/medium/low/none 四层 |
| OCR 初始化安全 | 多线程竞态崩溃 | 双重检查锁+主线程预加载 |