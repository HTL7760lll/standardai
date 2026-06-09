# Changelog

## 2026-06-09

### Bug 修复

- `_detect_major_sections()` 中文后 `\b` 正则失效，导致章节大面积漏检。移除 `\b`，新增 3 层级联检测（GB/T 格式 → 通用标题 → 启发式短行）
- 章节检测失败时整篇文档被归入封面截断到 500 字，丢失 95%+ 内容。`_chunk_cover()` 新增内容量守卫（>2000 字自动回退段落切片）
- 18 万字文档无结构时塞进 1 个 chunk。新增 `_chunk_fallback_paragraphs()` 段落级兜底，`smart_split_v2()` 增加最小切片保障
- `_is_text_garbled()` 阈值太低（20%），扫描件编码垃圾（/G21/G22 模式）骗过检测。提升到 40%，新增连续乱码序列、伪 CJK 字符、重复编码模式检测
- PaddleOCR 多线程竞态初始化导致 segfault。`_get_paddleocr()` 新增双重检查锁，`_ocr_pdf_with_paddle()` 主线程预初始化
- PaddlePaddle 3.3.1 的 PIR executor 与 PaddleOCR 不兼容导致 OCR 崩溃。新增 OCR 降级模式：失败时返回原文+警告，不阻塞上传
- 关键词检索无 IDF 加权，通用词污染所有结果。新增 `_compute_idf_weights()` 预计算 IDF 缓存
- 关键词分数完全相同无区分度。改为多因子评分（IDF 加权 + 匹配密度 + 位置加分 + 完整短语命中）
- 混合检索用 `max()` 简单合并无交叉验证。改为 RRF 融合 + 4 维加权置信度判定
- 无检索置信度兜底，低质量结果直接传 LLM 产生幻觉。新增 high/medium/low/none 四层，low 自动拦截
- `sentence-transformers 5.5.1` + `transformers 5.10.2` 的 `encode()` API 不兼容导致 embedding 生成报错。降级至 3.3.1

### 新增功能

- 文档类型自动分类 `_classify_document_type()`：national_standard / industry_standard / enterprise_standard / thesis / generic
- 4 套类型感知切片策略：国标条款层级 / 企业灵活编号 / 论文章节 / 通用段落兜底
- DOCX 嵌入图片 OCR 提取 `_extract_docx_images()` + `_ocr_single_image()`
- 零结果查询扩展 `_expand_query_synonyms()`：自动去掉疑问词重试
- 上传和切片接口返回 `document_type` 字段
- `/ask` 和 `/ask/stream` 响应新增 `retrieval_confidence` + `confidence_detail`

### 代码清理

- 删除无效函数：`smart_split_text`、`_find_split_boundary`、`extract_keyword`、`patch_document_by_id`、`delete_document_by_id`
- 合并重复函数：`create_document` + `loading_information` → `create_document`；移除 `download_document`、`patch_document_filename`（复用 `get_document_by_id`、`find_document`）
- `/ask` 和 `/ask/stream` 中 ~160 行重复引用构建代码提取为 `_build_references()` + `_make_ref()`
- 共减少约 310 行
