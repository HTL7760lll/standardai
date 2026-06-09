<template>
  <div class="app-shell">
    <!-- ═══════════ 顶部导航栏 ═══════════ -->
    <header class="top-bar">
      <div class="top-bar-left">
        <span class="logo-icon">📋</span>
        <h1 class="app-title">智能标准文档管理与 RAG 问答系统</h1>
      </div>
      <nav class="top-nav">
        <button :class="['nav-tab', { active: activeView === 'qa' }]" @click="switchView('qa')">
          💬 智能问答
        </button>
        <button :class="['nav-tab', { active: activeView === 'docs' }]" @click="switchView('docs')">
          📁 标准文档库
        </button>
        <button :class="['nav-tab', { active: activeView === 'watchdog' }]" @click="switchView('watchdog')">
          🔍 标准动态监控
        </button>
        <a href="https://std.samr.gov.cn/" target="_blank" class="nav-link" title="国家标准全文公开系统">
          🔗 国标公开平台
        </a>
      </nav>
    </header>

    <!-- ═══════════ 智能问答视图 ═══════════ -->
    <div v-if="activeView === 'qa'" class="qa-view">
      <div class="qa-chat-container">
        <!-- 聊天区域 -->
        <div class="chat-messages" ref="chatContainer">
          <div v-if="chatHistory.length === 0" class="chat-empty">
            <div class="empty-icon">💬</div>
            <div class="empty-text">欢迎使用智能标准文档问答</div>
            <div class="empty-sub">选择一个问题开始，或直接输入您的问题</div>
            <div class="suggested-questions">
              <el-button v-for="(sq, si) in suggestedQuestions" :key="si" size="small"
                class="suggested-btn" @click="clickFollowUp(sq)">{{ sq }}</el-button>
            </div>
          </div>

          <div v-for="(msg, idx) in chatHistory" :key="idx" :class="['chat-item', msg.role === 'user' ? 'chat-item-user' : 'chat-item-ai']">
            <div :class="['chat-bubble', msg.role === 'user' ? 'bubble-user' : 'bubble-ai']">
              <div class="bubble-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
              <div class="bubble-content">
                <div class="bubble-text">{{ msg.content }}</div>
              </div>
            </div>
            <!-- 自动文档匹配提示 -->
            <div v-if="msg.role === 'ai' && msg.autoMatched && !msg.autoMatchFallback" class="auto-match-banner">
              💡 检测到您的问题涉及「{{ msg.autoMatched.filename }}」，已自动限定检索范围
            </div>
            <div v-if="msg.role === 'ai' && msg.autoMatched && msg.autoMatchFallback" class="auto-match-banner auto-match-fallback">
              ⚠️ 检测到您可能想问「{{ msg.autoMatched.filename }}」，但该文档暂未生成切片，已切换至全库搜索。<br/>
              <span style="font-size:12px;">提示：请先到文档库对该文档点击"分析"生成切片后重试。</span>
            </div>

            <!-- 流式生成中指示 -->
            <div v-if="msg.role === 'ai' && msg.streaming" class="streaming-indicator">
              <span class="streaming-dot"></span> AI 正在生成回答...
            </div>

            <!-- 引用来源放在气泡外面（仅 AI 消息，非流式中） -->
            <div v-if="msg.role === 'ai' && !msg.streaming && msg.references && msg.references.length" class="ref-outside">
              <el-collapse>
                <el-collapse-item>
                  <template #title>
                    <div class="ref-toggle-title">
                      📎 数据来源 ·
                      <span class="ref-count">{{ msg.references.length }} 条参考资料</span>
                      <span class="ref-first">— {{ msg.references[0].filename || '未知文件' }}</span>
                    </div>
                  </template>
                  <div v-for="(ref, ri) in msg.references" :key="ri" class="ref-outside-item">
                    <div class="ref-outside-header">
                      <el-tag size="small" :type="ref.match_type === 'keyword' ? 'warning' : ref.match_type === 'semantic' ? 'success' : 'info'">
                        {{ ref.match_type === 'keyword' ? '关键词' : ref.match_type === 'semantic' ? '语义' : ref.match_type === 'hybrid' ? '混合' : '关联' }}
                      </el-tag>
                      <span class="ref-outside-file">{{ ref.filename }}</span>
                      <span class="ref-outside-score" v-if="ref.score !== undefined">
                        匹配度 {{ (ref.score * 100).toFixed(0) }}%
                      </span>
                    </div>
                    <div class="ref-outside-text">{{ ref.content_preview?.substring(0, 250) }}</div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <!-- 追问建议（仅 AI 消息，非流式中） -->
            <div v-if="msg.role === 'ai' && !msg.streaming && msg.followUps && msg.followUps.length" class="follow-ups">
              <div class="follow-ups-label">💡 您可能还想了解：</div>
              <el-button v-for="(fu, fi) in msg.followUps" :key="fi" size="small" text type="primary"
                class="follow-up-btn" @click="clickFollowUp(fu)">{{ fu }}</el-button>
            </div>

            <!-- 相关推荐（仅 AI 消息，非流式中） -->
            <div v-if="msg.role === 'ai' && !msg.streaming && msg.recommendations" class="recommendations-box">
              <div class="rec-title">📖 相关标准推荐</div>
              <div v-if="msg.recommendations.same_industry?.length" class="rec-group">
                <div class="rec-group-label">🔥 同行业标准</div>
                <div v-for="rec in msg.recommendations.same_industry" :key="rec.document_id" class="rec-item"
                  @click="selectRecommendedDoc(rec)">
                  <span class="rec-filename">{{ rec.filename }}</span>
                  <span class="rec-reason">{{ rec.reason }}</span>
                </div>
              </div>
              <div v-if="msg.recommendations.semantic_similar?.length" class="rec-group">
                <div class="rec-group-label">🧠 内容相关推荐</div>
                <div v-for="rec in msg.recommendations.semantic_similar" :key="rec.document_id" class="rec-item"
                  @click="selectRecommendedDoc(rec)">
                  <span class="rec-filename">{{ rec.filename }}</span>
                  <span class="rec-score">{{ (rec.score * 100).toFixed(0) }}%</span>
                  <span class="rec-reason">{{ rec.reason }}</span>
                </div>
              </div>
              <div v-if="msg.recommendations.cited_references?.length" class="rec-group">
                <div class="rec-group-label">📖 当前标准引用</div>
                <div v-for="rec in msg.recommendations.cited_references" :key="rec.document_id" class="rec-item"
                  @click="selectRecommendedDoc(rec)">
                  <span class="rec-filename">{{ rec.filename }}</span>
                  <span class="rec-reason">{{ rec.reason }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区域 -->
        <div class="chat-input-area">
          <div class="input-row">
            <el-input
              v-model="question"
              type="textarea"
              :rows="2"
              placeholder="输入您想了解的标准条款、指标或要求..."
              resize="none"
              @keydown.enter.exact.prevent="submitAsk"
              class="chat-input"
            />
          </div>
          <div class="input-actions">
            <div class="input-left-actions">
              <el-tooltip content="控制检索返回的参考资料数量，越多可能召回更全但速度略慢（建议3-10）" placement="top">
                <span class="limit-label">📚 参考数量</span>
              </el-tooltip>
              <el-input-number v-model="limit" :min="1" :max="20" size="small" controls-position="right" />
              <el-tooltip content="选择某份标准后，AI 将只从该标准中检索答案，不勾选则搜索全部标准" placement="top">
                <el-select v-model="askDocId" placeholder="限定文档（可留空）" clearable size="small" style="width: 200px;">
                  <el-option v-for="doc in allDocuments" :key="doc.id" :label="doc.filename" :value="doc.id" />
                </el-select>
              </el-tooltip>
            </div>
            <el-button type="primary" :loading="asking" @click="submitAsk" class="send-btn">发送</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════ 文档库视图 ═══════════ -->
    <div v-if="activeView === 'docs'" class="docs-view">
      <!-- 搜索栏 -->
      <div class="docs-toolbar">
        <div class="toolbar-left">
          <el-input v-model="searchKeyword" placeholder="搜索文件名..." clearable size="default"
            style="width: 220px;" @clear="loadDocuments" @keydown.enter="loadDocuments">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="filterStandardType" placeholder="标准类型" clearable size="default"
            style="width: 160px;" @change="loadDocuments">
            <el-option label="强制性国家标准" value="强制性国家标准" />
            <el-option label="推荐性国家标准" value="推荐性国家标准" />
            <el-option label="行业标准" value="行业标准" />
            <el-option label="地方标准" value="地方标准" />
            <el-option label="团体标准" value="团体标准" />
            <el-option label="企业标准" value="企业标准" />
            <el-option label="国际标准" value="国际标准" />
          </el-select>
          <el-select v-model="filterIndustry" placeholder="所属行业" clearable size="default"
            style="width: 150px;" @change="loadDocuments">
            <el-option label="信息技术" value="信息技术" />
            <el-option label="制造业" value="制造业" />
            <el-option label="工程建设" value="工程建设" />
            <el-option label="能源" value="能源" />
            <el-option label="安全生产" value="安全生产" />
            <el-option label="环境保护" value="环境保护" />
            <el-option label="交通运" value="交通运输" />
            <el-option label="食品" value="食品" />
            <el-option label="医疗器械" value="医疗器械" />
            <el-option label="农林牧渔" value="农林牧渔" />
            <el-option label="教育" value="教育" />
            <el-option label="金融" value="金融" />
            <el-option label="生物技术" value="生物技术" />
            <el-option label="通用管理" value="通用管理" />
          </el-select>
          <el-button type="primary" @click="loadDocuments">搜索</el-button>
        </div>
        <div class="toolbar-right">
          <el-button type="success" @click="showUploadDialog = true">
            <el-icon><Upload /></el-icon> 上传文档
          </el-button>
          <el-button @click="loadDocuments" :loading="loadingDocuments">刷新</el-button>
        </div>
      </div>

      <!-- 统计卡片 + 饼图 -->
      <div class="docs-stats-area">
        <div class="stats-cards">
          <div class="stat-card"><div class="stat-num">{{ totalDocuments }}</div><div class="stat-label">文档总数</div></div>
          <div class="stat-card"><div class="stat-num">{{ Object.keys(statsData.standard_types || {}).length }}</div><div class="stat-label">标准类型</div></div>
          <div class="stat-card"><div class="stat-num">{{ Object.keys(statsData.industries || {}).length }}</div><div class="stat-label">涉及行业</div></div>
        </div>
        <div class="charts-row">
          <div class="chart-box" ref="typeChartRef"></div>
          <div class="chart-box" ref="industryChartRef"></div>
        </div>
      </div>

      <!-- 文档表格 -->
      <el-table :data="documents" border stripe style="width: 100%"
        empty-text="暂无文档，请先上传" v-loading="loadingDocuments"
        @row-click="showDocDetail" row-class-name="doc-row">
        <el-table-column label="序号" width="60" align="center">
          <template #default="{ $index }">{{ (docPage - 1) * docPageSize + $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="filename" label="文件名" min-width="280" show-overflow-tooltip />
        <el-table-column prop="standard_type" label="标准类型" width="140" align="center" />
        <el-table-column prop="industry" label="行业" width="120" align="center" />
        <el-table-column prop="created_at" label="上传时间" width="170" align="center">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="270" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click.stop="handleRegisterWatchdog(row)">监控</el-button>
            <el-button size="small" text type="success" :loading="chunkLoadingId === row.id" @click.stop="handleGenerateChunks(row)">切片</el-button>
            <el-button size="small" text type="warning" @click.stop="handleAnalyze(row)">分析</el-button>
            <el-button size="small" text type="danger" @click.stop="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination v-model:current-page="docPage" :page-size="docPageSize"
          :total="totalDocuments" layout="total, prev, pager, next, jumper"
          @current-change="loadDocuments" background />
      </div>
    </div>

    <!-- ═══════════ 标准动态监控视图 ═══════════ -->
    <div v-if="activeView === 'watchdog'" class="watchdog-view">
      <div class="watchdog-toolbar">
        <el-select v-model="watchdogFilter" placeholder="按状态筛选" clearable size="default" style="width:180px;" @change="loadWatchdog">
          <el-option label="现行有效" value="active" />
          <el-option label="即将废止" value="expiring" />
          <el-option label="已废止" value="abolished" />
          <el-option label="已被替代" value="replaced" />
          <el-option label="状态未知" value="unknown" />
        </el-select>
        <el-button type="primary" @click="loadWatchdog">查询</el-button>
        <el-button :loading="batchChecking" @click="triggerBatchCheck">批量检查</el-button>
        <el-button :loading="backfilling" @click="backfillAll">一键回填已有文档</el-button>
      </div>

      <el-table :data="watchdogList" border stripe style="width:100%;" v-loading="loadingWatchdog" empty-text="暂无标准版本记录">
        <el-table-column label="序号" width="60" align="center">
          <template #default="{ $index }">{{ (wdPage - 1) * wdPageSize + $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="standard_number" label="标准编号" width="160" />
        <el-table-column prop="standard_name" label="标准名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="filename" label="关联文件" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="替代标准" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.replaced_by_number || '-' }}</template>
        </el-table-column>
        <el-table-column label="最后检查" width="160" align="center">
          <template #default="{ row }">{{ formatDate(row.last_checked) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center">
          <template #default="{ row }">
            <el-button size="small" text @click="handleCheckOne(row)">检查</el-button>
            <el-button size="small" text type="warning" @click="handleUpdateStatus(row)">更新状态</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination v-model:current-page="wdPage" :page-size="wdPageSize"
          :total="wdTotal" layout="total, prev, pager, next" @current-change="loadWatchdog" background />
      </div>
    </div>

    <!-- ═══════════ 上传弹窗 ═══════════ -->
    <el-dialog v-model="showUploadDialog" title="上传标准文档" width="520px" :close-on-click-modal="false">
      <el-form label-position="top" size="default">
        <el-form-item label="标准类型">
          <el-select v-model="uploadForm.standard_type" placeholder="请选择标准类型" clearable filterable allow-create style="width: 100%;">
            <el-option-group label="国家标准">
              <el-option label="强制性国家标准 (GB)" value="强制性国家标准" />
              <el-option label="推荐性国家标准 (GB/T)" value="推荐性国家标准" />
            </el-option-group>
            <el-option-group label="行业/地方">
              <el-option label="行业标准" value="行业标准" />
              <el-option label="地方标准" value="地方标准" />
            </el-option-group>
            <el-option-group label="其他">
              <el-option label="团体标准" value="团体标准" />
              <el-option label="企业标准" value="企业标准" />
              <el-option label="国际标准" value="国际标准" />
              <el-option label="其他标准" value="其他标准" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="所属行业">
          <el-select v-model="uploadForm.industry" placeholder="请选择所属行业" clearable filterable allow-create style="width: 100%;">
            <el-option label="信息技术" value="信息技术" />
            <el-option label="制造业" value="制造业" />
            <el-option label="工程建设" value="工程建设" />
            <el-option label="能源" value="能源" />
            <el-option label="安全生产" value="安全生产" />
            <el-option label="环境保护" value="环境保护" />
            <el-option label="交通运输" value="交通运输" />
            <el-option label="食品" value="食品" />
            <el-option label="医疗器械" value="医疗器械" />
            <el-option label="农林牧渔" value="农林牧渔" />
            <el-option label="教育" value="教育" />
            <el-option label="金融" value="金融" />
            <el-option label="生物技术" value="生物技术" />
            <el-option label="通用管理" value="通用管理" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="uploadForm.tags" placeholder="多个标签请使用英文逗号分隔，例如：AI,云服务,安全" />
        </el-form-item>
        <el-upload drag :auto-upload="false" :limit="1" :on-change="handleFileChange" :on-remove="handleFileRemove">
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽文件或点击选择</div>
          <template #tip><div class="el-upload__tip">仅支持 PDF / DOCX / TXT 格式</div></template>
        </el-upload>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload" size="default">确认上传</el-button>
      </template>
    </el-dialog>

    <!-- ═══════════ 文档详情弹窗 ═══════════ -->
    <el-dialog v-model="showDetailDialog" :title="detailDoc?.filename" width="600px">
      <template v-if="detailDoc">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="文件名">{{ detailDoc.filename }}</el-descriptions-item>
          <el-descriptions-item label="标准类型">{{ detailDoc.standard_type }}</el-descriptions-item>
          <el-descriptions-item label="行业">{{ detailDoc.industry }}</el-descriptions-item>
          <el-descriptions-item label="标签">{{ (detailDoc.tags || []).join('、') || '无' }}</el-descriptions-item>
          <el-descriptions-item label="上传时间" :span="2">{{ formatDate(detailDoc.created_at) }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-dialog>

    <!-- ═══════════ 分析结果弹窗 ═══════════ -->
    <el-dialog v-model="showAnalysisDialog" title="文档智能分析" width="640px">
      <template v-if="analysisResult">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="标准名称">{{ analysisResult.standard_name || analysisDocName || '-' }}</el-descriptions-item>
          <el-descriptions-item label="标准编号">{{ analysisResult.standard_number || analysisDocNumber || '-' }}</el-descriptions-item>
          <el-descriptions-item label="标准类型">{{ analysisResult.standard_type_guess || '-' }}</el-descriptions-item>
          <el-descriptions-item label="所属行业">{{ analysisResult.industry_guess || '-' }}</el-descriptions-item>
          <el-descriptions-item label="适用范围" :span="2">{{ analysisResult.scope || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top:14px;"><strong>摘要：</strong><p style="line-height:1.8;color:#606266;">{{ analysisResult.summary }}</p></div>
        <div v-if="analysisResult.keywords" style="margin-top:8px;">
          <strong>关键词：</strong>
          <el-tag v-for="(kw,i) in analysisResult.keywords.split(',')" :key="i" size="small" style="margin:2px 4px;">{{ kw.trim() }}</el-tag>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Upload, Search } from '@element-plus/icons-vue'
import { askQuestion, askStream, generateChunks, getDocuments, uploadDocument, analyzeDocument, getStandardsStatus, triggerStandardCheck, triggerBatchCheck as apiTriggerBatchCheck, updateStandardStatus } from './services/api'
import axios from 'axios'
import * as echarts from 'echarts'

// ── 视图 ──
const activeView = ref('qa')
const chatHistory = ref([])
const chatContainer = ref(null)

// ── 文档 ──
const documents = ref([])
const allDocuments = ref([])
const totalDocuments = ref(0)
const loadingDocuments = ref(false)
const docPage = ref(1)
const docPageSize = ref(10)
const searchKeyword = ref('')
const filterStandardType = ref('')
const filterIndustry = ref('')
const statsData = ref({})

// ── 上传 ──
const uploading = ref(false)
const selectedFile = ref(null)
const showUploadDialog = ref(false)
const uploadForm = reactive({ standard_type: '', industry: '', tags: '' })

// ── 问答 ──
const question = ref('')
const limit = ref(5)
const asking = ref(false)
const askDocId = ref(null)

// ── 切片 ──
const chunkLoadingId = ref(null)

// ── 弹窗 ──
const showDetailDialog = ref(false)
const detailDoc = ref(null)
const showAnalysisDialog = ref(false)
const analysisResult = ref(null)
const analysisDocName = ref('')
const analysisDocNumber = ref('')

// ── 欢迎引导问题 ──
const suggestedQuestions = ref([
  '这个标准引用了哪些相关标准？',
  '标准适用于哪些产品或场景？',
  '有哪些核心指标和参数要求？',
  '有哪些强制性规定和禁止性条款？',
  '第1条/第一章主要讲了什么？',
])

// ── 标准监控 ──
const watchdogList = ref([])
const wdTotal = ref(0)
const wdPage = ref(1)
const wdPageSize = ref(15)
const watchdogFilter = ref('')
const loadingWatchdog = ref(false)
const batchChecking = ref(false)
const backfilling = ref(false)

// ── 图表 ──
const typeChartRef = ref(null)
const industryChartRef = ref(null)
let typeChart = null
let industryChart = null

// ═══════════ 方法 ═══════════

function switchView(view) {
  activeView.value = view
  if (view === 'docs') { loadDocuments() }
  if (view === 'qa') { loadAllDocuments() }
  if (view === 'watchdog') { loadWatchdog() }
}

function formatDate(str) {
  if (!str) return '-'
  try { return new Date(str).toLocaleString('zh-CN', { hour12: false }) } catch { return str }
}

function handleFileChange(file) { selectedFile.value = file.raw }
function handleFileRemove() { selectedFile.value = null }

async function loadDocuments() {
  loadingDocuments.value = true
  try {
    if (searchKeyword.value) {
      const res = await axios.get('http://127.0.0.1:8000/documents/search', {
        params: { keyword: searchKeyword.value, page: docPage.value, page_size: docPageSize.value }
      })
      documents.value = res.data.documents || []
      totalDocuments.value = res.data.total_count || 0
    } else {
      const params = { page: docPage.value, page_size: docPageSize.value }
      if (filterStandardType.value) params.standard_type = filterStandardType.value
      if (filterIndustry.value) params.industry = filterIndustry.value
      const res = await getDocuments(params)
      const data = res.data
      if (Array.isArray(data)) { documents.value = data; totalDocuments.value = data.length }
      else if (data.documents) { documents.value = data.documents; totalDocuments.value = data.total_count ?? data.documents.length }
      else { documents.value = []; totalDocuments.value = 0 }
    }
    // 加载统计 & 刷新饼图
    try {
      const sr = await axios.get('http://127.0.0.1:8000/documents/stats')
      statsData.value = sr.data
      await nextTick()
      renderCharts()
    } catch {}
  } catch {
    ElMessage.error('文档列表加载失败')
  } finally { loadingDocuments.value = false }
}

async function loadAllDocuments() {
  try {
    const res = await getDocuments({ page: 1, page_size: 200 })
    const data = res.data
    allDocuments.value = data.documents || (Array.isArray(data) ? data : [])
  } catch {}
}

// ── 饼图渲染 ──
function renderCharts() {
  // 先销毁旧实例
  if (typeChart) { typeChart.dispose(); typeChart = null }
  if (industryChart) { industryChart.dispose(); industryChart = null }

  const typeData = statsData.value.standard_types || {}
  const indData = statsData.value.industries || {}

  if (typeChartRef.value) {
    typeChart = echarts.init(typeChartRef.value)
    typeChart.setOption({
      title: { text: '标准类型分布', left: 'center', textStyle: { fontSize: 14, color: '#1a3a5c' } },
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['50%', '55%'],
        data: Object.entries(typeData).map(([k, v]) => ({ name: k, value: v })),
        label: { formatter: '{b}\n{d}%', fontSize: 11 },
        emphasis: { label: { fontSize: 14 } }
      }],
      color: ['#2d6aa0', '#42a5f5', '#66bb6a', '#ffa726', '#ef5350', '#ab47bc', '#26c6da', '#9ccc65']
    })
  }

  if (industryChartRef.value) {
    industryChart = echarts.init(industryChartRef.value)
    industryChart.setOption({
      title: { text: '行业分布', left: 'center', textStyle: { fontSize: 14, color: '#1a3a5c' } },
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['50%', '55%'],
        data: Object.entries(indData).map(([k, v]) => ({ name: k, value: v })),
        label: { formatter: '{b}\n{d}%', fontSize: 11 },
        emphasis: { label: { fontSize: 14 } }
      }],
      color: ['#42a5f5', '#66bb6a', '#ffa726', '#ef5350', '#ab47bc', '#2d6aa0', '#26c6da', '#9ccc65']
    })
  }
}

// ── 上传 ──
async function submitUpload() {
  if (!selectedFile.value) { ElMessage.warning('请先选择文件'); return }
  const fd = new FormData()
  fd.append('file', selectedFile.value)
  if (uploadForm.standard_type) fd.append('standard_type', uploadForm.standard_type)
  if (uploadForm.industry) fd.append('industry', uploadForm.industry)
  if (uploadForm.tags) fd.append('tags', uploadForm.tags)
  uploading.value = true
  try {
    const uploadRes = await uploadDocument(fd)
    const newDocId = uploadRes.data?.document?.id
    const autoChunk = uploadRes.data?.auto_chunk
    const chunkError = uploadRes.data?.chunk_error
    selectedFile.value = null; uploadForm.standard_type = ''; uploadForm.industry = ''; uploadForm.tags = ''
    showUploadDialog.value = false; docPage.value = 1
    if (autoChunk) {
      ElMessage.success(`上传成功！自动生成 ${autoChunk.total_chunks} 条切片`)
    } else if (chunkError) {
      ElMessage.warning(`上传成功，但自动切片失败：${chunkError}`)
    } else {
      ElMessage.success('上传成功')
    }
    await loadDocuments(); await loadAllDocuments()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '上传失败') }
  finally { uploading.value = false }
}

// ── 切片/分析/删除 ──
async function handleGenerateChunks(row) {
  chunkLoadingId.value = row.id
  try {
    const res = await generateChunks(row.id)
    ElMessage.success(`切片生成成功，共 ${res.data.total_chunks ?? '若干'} 条`)
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '生成切片失败') }
  finally { chunkLoadingId.value = null }
}

async function handleAnalyze(row) {
  try {
    // 从文件名提取标准名称和编号作为兜底
    const fname = row.filename || ''
    analysisDocName.value = fname.replace(/\.(pdf|docx|txt)$/i, '')
    const numMatch = fname.match(/GB[\/\s]*T?\s*\d+[\.\-]?\d*/i) || fname.match(/\d{4,}[\.\-]?\d*/)
    analysisDocNumber.value = numMatch ? numMatch[0] : ''
    const res = await axios.post(`http://127.0.0.1:8000/documents/${row.id}/analyze`)
    analysisResult.value = res.data.analysis
    showAnalysisDialog.value = true
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '分析失败，请先生成切片') }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定要删除「${row.filename}」吗？此操作不可恢复。`, '确认删除', {
      type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消'
    })
    await axios.delete(`http://127.0.0.1:8000/documents/${row.id}`)
    ElMessage.success('删除成功')
    await loadDocuments(); await loadAllDocuments()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(e?.response?.data?.detail || '删除失败')
    }
  }
}

function showDocDetail(row) { detailDoc.value = row; showDetailDialog.value = true }

// ── 问答（流式版）──
async function submitAsk() {
  if (!question.value.trim()) { ElMessage.warning('请输入问题'); return }
  asking.value = true
  const q = question.value.trim()
  question.value = ''
  chatHistory.value.push({ role: 'user', content: q })

  // 创建 AI 消息占位，标记为流式中
  const aiMsg = { role: 'ai', content: '', references: [], followUps: [], recommendations: null, streaming: true }
  chatHistory.value.push(aiMsg)

  const scrollToBottom = () => {
    nextTick(() => {
      if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    })
  }

  try {
    const payload = { question: q, limit: limit.value, document_id: askDocId.value || null }
    for await (const event of askStream(payload)) {
      if (event.type === 'token') {
        aiMsg.content += event.content
        scrollToBottom()
      } else if (event.type === 'meta') {
        aiMsg.references = event.references || []
        aiMsg.followUps = event.follow_up_questions || []
        aiMsg.recommendations = event.recommendations || null
        // 自动文档匹配：同步 askDocId + 显示提示
        if (event.auto_matched_document) {
          askDocId.value = event.auto_matched_document.document_id
          aiMsg.autoMatched = event.auto_matched_document
        }
        if (event.auto_match_fallback) {
          aiMsg.autoMatchFallback = true
        }
      } else if (event.type === 'answer') {
        // 无参考资料时的兜底回答
        aiMsg.content = event.content
      } else if (event.type === 'done') {
        aiMsg.streaming = false
      } else if (event.type === 'error') {
        aiMsg.content += '\n\n[生成中断: ' + event.message + ']'
      }
    }
  } catch (e) {
    aiMsg.content = aiMsg.content || ('抱歉，请求失败：' + (e?.message || '未知错误'))
    aiMsg.streaming = false
  } finally {
    aiMsg.streaming = false
    asking.value = false
    scrollToBottom()
  }
}

// ── 追问/推荐交互 ──
function clickFollowUp(text) {
  question.value = text
  submitAsk()
}

function selectRecommendedDoc(rec) {
  askDocId.value = rec.document_id
  ElMessage.success('已切换到标准: ' + rec.filename + '（下次提问将基于此标准）')
}

// ── 标准监控 ──
function statusTagType(status) {
  const map = { active: 'success', expiring: 'warning', replaced: 'info', abolished: 'danger', unknown: '' }
  return map[status] || ''
}

function statusLabel(status) {
  const map = { active: '🟢 现行有效', expiring: '🟡 即将废止', replaced: '🔵 已被替代', abolished: '🔴 已废止', unknown: '⚪ 未知' }
  return map[status] || status
}

async function loadWatchdog() {
  loadingWatchdog.value = true
  try {
    const params = { page: wdPage.value, page_size: wdPageSize.value }
    if (watchdogFilter.value) params.status = watchdogFilter.value
    const res = await getStandardsStatus(params)
    watchdogList.value = res.data.standards || []
    wdTotal.value = res.data.total || 0
  } catch {
    ElMessage.error('加载标准监控列表失败')
  } finally { loadingWatchdog.value = false }
}

async function handleCheckOne(row) {
  try {
    const res = await triggerStandardCheck(row.id)
    ElMessage.success(`检查完成：${res.data.status}`)
    await loadWatchdog()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '检查失败') }
}

async function handleUpdateStatus(row) {
  ElMessageBox.prompt('请输入新状态 (active / expiring / replaced / abolished)', '更新标准状态', {
    confirmButtonText: '确认', cancelButtonText: '取消',
    inputValue: row.status,
  }).then(async ({ value }) => {
    try {
      await updateStandardStatus(row.id, { new_status: value })
      ElMessage.success('状态更新成功')
      await loadWatchdog()
    } catch (e) { ElMessage.error(e?.response?.data?.detail || '更新失败') }
  }).catch(() => {})
}

async function triggerBatchCheck() {
  batchChecking.value = true
  try {
    const res = await apiTriggerBatchCheck()
    ElMessage.success(`批量检查完成：已检查 ${res.data.checked} 条，更新 ${res.data.updated} 条`)
    await loadWatchdog()
  } catch { ElMessage.error('批量检查失败') }
  finally { batchChecking.value = false }
}

async function backfillAll() {
  backfilling.value = true
  try {
    const res = await axios.post('http://127.0.0.1:8000/standards/watchdog/backfill-all')
    ElMessage.success(`回填完成：共 ${res.data.total} 条文档，注册 ${res.data.registered} 条，跳过 ${res.data.skipped} 条`)
    await loadWatchdog()
  } catch { ElMessage.error('回填失败') }
  finally { backfilling.value = false }
}

async function handleRegisterWatchdog(row) {
  try {
    await axios.post(`http://127.0.0.1:8000/standards/watchdog/register/${row.id}`)
    ElMessage.success(`「${row.filename}」已注册到标准监控`)
  } catch (e) { ElMessage.warning(e?.response?.data?.detail || '注册失败，请确保文件名包含标准编号') }
}

// ── 窗口缩放时重绘饼图 ──
window.addEventListener('resize', () => { typeChart?.resize(); industryChart?.resize() })

// ── 视图切换时重绘饼图 ──
watch(activeView, (v) => {
  if (v === 'docs') {
    setTimeout(() => {
      if (statsData.value && (Object.keys(statsData.value.standard_types || {}).length || Object.keys(statsData.value.industries || {}).length)) {
        renderCharts()
      }
    }, 300)
  }
})

// statsData 更新时也重绘（如果当前在文档库视图）
watch(statsData, () => {
  if (activeView.value === 'docs') {
    setTimeout(() => renderCharts(), 200)
  }
}, { deep: true })

onMounted(() => {
  loadAllDocuments()
  axios.get('http://127.0.0.1:8000/documents/stats').then(sr => {
    statsData.value = sr.data
    nextTick(() => renderCharts())
  }).catch(() => {})
})
</script>
