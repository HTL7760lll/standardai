<template>
  <div class="app-shell">
    <!-- ═══════════ 登录遮罩 ═══════════ -->
    <div v-if="!loggedIn" class="login-overlay">
      <div class="login-card">
        <!-- 左侧品牌区 -->
        <div class="login-brand">
          <div class="login-brand-icon">📋</div>
          <div class="login-brand-title">智能标准文档管理</div>
          <div class="login-brand-sub">与 RAG 问答系统</div>
          <div class="login-brand-desc">面向标准工程师和研究人员的 AI 助手</div>
        </div>
        <!-- 右侧表单区 -->
        <div class="login-form-panel">
          <div class="login-tabs">
            <span :class="['login-tab', { active: loginMode === 'login' }]" @click="loginMode='login';loginError=''">登录</span>
            <span :class="['login-tab', { active: loginMode === 'register' }]" @click="loginMode='register';loginError=''">注册</span>
          </div>
          <el-input v-model="loginForm.username" placeholder="用户名" size="large" style="margin-bottom:16px;">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
          <el-input v-model="loginForm.password" type="password" placeholder="密码" size="large" show-password style="margin-bottom:16px;" @keydown.enter="handleAuth">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
          <el-input v-if="loginMode === 'register'" v-model="loginForm.confirm" type="password" placeholder="确认密码" size="large" show-password style="margin-bottom:16px;" @keydown.enter="handleAuth">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
          <p v-if="loginError" class="login-error">{{ loginError }}</p>
          <el-button type="primary" size="large" :loading="loginLoading" @click="handleAuth" style="width:100%;">
            {{ loginMode === 'login' ? '登 录' : '注 册' }}
          </el-button>
        </div>
      </div>
    </div>

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
        <a href="https://std.samr.gov.cn/" target="_blank" class="nav-link" title="国家标准全文公开系统">
          🔗 国标公开平台
        </a>
        <span style="color:#c8d8e8;font-size:13px;margin-left:12px;">
          👤 {{ currentUser }}
          <el-tag size="small" :type="currentRole==='admin'?'danger':currentRole==='engineer'?'warning':'info'" style="margin-left:4px;vertical-align:middle;">{{ currentRole==='admin'?'管理员':currentRole==='engineer'?'工程师':'访客' }}</el-tag>
        </span>
        <el-button text size="small" style="color:#c8d8e8;" @click="doLogout">退出</el-button>
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
                <div class="bubble-text" v-if="msg.role === 'user'">{{ msg.content }}</div>
                <div class="bubble-text markdown-body" v-else v-html="renderMarkdown(msg.content)"></div>
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
              <span class="streaming-dot"></span>
              {{ msg.refsCount ? '已检索到 ' + msg.refsCount + ' 条参考，' : '' }}AI 正在生成回答...
            </div>

            <!-- 错误重试 -->
            <div v-if="msg.role === 'ai' && msg.isError && !msg.streaming" style="margin-top:6px;">
              <el-button size="small" type="warning" text @click="retryAsk(msg)">🔄 重新生成</el-button>
            </div>

            <!-- 对比模式标签 -->
            <div v-if="msg.role === 'ai' && msg.isComparison && !msg.streaming" class="comparison-banner">
              🔍 对比模式：已同时检索 {{ msg.comparisonCount }} 份标准
            </div>

            <!-- 引用来源（仅 AI 消息，非流式中） -->
            <div v-if="msg.role === 'ai' && !msg.streaming && msg.references && msg.references.length" class="ref-outside">
              <!-- 对比模式：按标准分组 -->
              <template v-if="msg.isComparison">
                <div class="ref-toggle-title" style="margin-bottom:8px;">
                  📎 对比来源 · <span class="ref-count">{{ msg.references.length }} 条</span>
                  <span class="ref-first">— {{ msg.comparisonCount }} 份标准</span>
                </div>
                <div v-for="(group, gIdx) in groupedRefs(msg.references)" :key="gIdx" class="ref-group-box">
                  <div class="ref-group-label">📋 {{ group.filename }}</div>
                  <div v-for="(ref, ri) in group.refs" :key="ri" class="ref-outside-item">
                    <div class="ref-outside-header">
                      <el-tag size="small" :type="ref.source_label === '直接命中' ? 'success' : 'info'">{{ ref.source_label || '参考' }}</el-tag>
                      <span class="ref-outside-score" v-if="ref.score !== undefined">{{ (ref.score * 100).toFixed(0) }}%</span>
                    </div>
                    <div class="ref-section-path" v-if="ref.section_path">📂 {{ ref.section_path }}</div>
                    <div class="ref-outside-text">{{ ref.content_preview?.substring(0, 250) }}</div>
                    <el-button size="small" text type="primary" style="margin-top:4px;" @click.stop="startAnnotation(ref)">✏️ 标注</el-button>
                  </div>
                </div>
              </template>
              <!-- 单标准模式 -->
              <template v-else>
                <el-collapse>
                  <el-collapse-item>
                    <template #title>
                      <div class="ref-toggle-title">
                        📎 数据来源 · <span class="ref-count">{{ msg.references.length }} 条</span>
                        <span class="ref-first">— {{ msg.references[0].filename || '未知文件' }}</span>
                      </div>
                    </template>
                    <div v-for="(ref, ri) in msg.references" :key="ri" class="ref-outside-item">
                      <div class="ref-outside-header">
                        <el-tag size="small" :type="ref.source_label === '直接命中' ? 'success' : 'info'">{{ ref.source_label || '参考' }}</el-tag>
                        <span class="ref-outside-file">{{ ref.filename }}</span>
                        <span class="ref-outside-score" v-if="ref.score !== undefined">{{ (ref.score * 100).toFixed(0) }}%</span>
                      </div>
                      <div class="ref-section-path" v-if="ref.section_path">📂 {{ ref.section_path }}</div>
                      <div class="ref-outside-text">{{ ref.content_preview?.substring(0, 250) }}</div>
                      <el-button size="small" text type="primary" style="margin-top:4px;" @click.stop="startAnnotation(ref)">✏️ 标注</el-button>
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </template>
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
              <el-tooltip content="选1份=单标准；选2-5份=跨标准对比；不选=全库" placement="top">
                <el-select v-model="askDocIds" placeholder="选择标准（可多选对比）" clearable multiple size="small" style="width: 280px;" :multiple-limit="5" collapse-tags>
                  <el-option v-for="doc in allDocuments" :key="doc.id" :label="doc.filename" :value="doc.id" />
                </el-select>
              </el-tooltip>
            </div>
            <el-button text size="small" @click="clearChat" :disabled="chatHistory.length === 0">清空对话</el-button>
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
          <el-button v-if="currentRole !== 'viewer'" type="success" @click="showUploadDialog = true">
            <el-icon><Upload /></el-icon> 上传文档
          </el-button>
          <el-button @click="loadDocuments" :loading="loadingDocuments">刷新</el-button>
          <el-button type="info" text @click="showCitationGraph">🔗 引用关系</el-button>
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
            <template v-if="currentRole !== 'viewer'">
              <el-button size="small" text type="success" :loading="chunkLoadingId === row.id" @click.stop="handleGenerateChunks(row)">切片</el-button>
              <el-button size="small" text type="warning" @click.stop="handleAnalyze(row)">分析</el-button>
              <el-button size="small" text type="info" @click.stop="openDraftCheck(row)">📝 起草辅助</el-button>
              <el-button v-if="currentRole === 'admin' || (currentRole === 'engineer')" size="small" text type="danger" @click.stop="handleDelete(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination v-model:current-page="docPage" :page-size="docPageSize"
          :total="totalDocuments" layout="total, prev, pager, next, jumper"
          @current-change="loadDocuments" background />
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

  <!-- ═══════════ 起草辅助弹窗 ═══════════ -->
  <el-dialog v-model="showDraftDialog" title="📝 起草辅助 — 条款冲突检查" width="600px">
    <div v-if="draftLoading" style="text-align:center;padding:20px;">加载条款列表中...</div>
    <div v-else-if="draftClauses.length === 0" style="text-align:center;padding:20px;color:#999;">该文档暂无条款（请先生成切片）</div>
    <div v-else>
      <p style="color:#909399;font-size:13px;margin-bottom:12px;">选择草案条款，自动检查是否与现行标准冲突：</p>
      <div v-for="cl in draftClauses" :key="cl.section_number" class="draft-clause-item"
           @click="checkDraftClause(cl)" style="cursor:pointer;padding:8px 12px;margin-bottom:6px;border:1px solid #e4e7ed;border-radius:6px;transition:all .2s;">
        <strong>{{ cl.section_number }}</strong>
        <span style="color:#909399;margin-left:8px;font-size:12px;">{{ cl.section_path }}</span>
      </div>
    </div>
    <p v-if="draftResult" style="margin-top:16px;white-space:pre-wrap;line-height:1.8;background:#f8f9fb;padding:12px;border-radius:6px;">{{ draftResult }}</p>
  </el-dialog>

  <!-- ═══════════ 标注弹窗 ═══════════ -->
  <el-dialog v-model="showAnnotationDialog" title="添加标注笔记" width="460px">
    <p style="color:#909399;font-size:13px;margin-bottom:8px;">
      📂 {{ annotationRef?.section_path || '未知章节' }}
    </p>
    <el-input v-model="annotationText" type="textarea" :rows="4" placeholder="输入你的标注笔记..." />
    <template #footer>
      <el-button @click="showAnnotationDialog = false">取消</el-button>
      <el-button type="primary" :loading="annotationSaving" @click="saveAnnotation">保存标注</el-button>
    </template>
  </el-dialog>

  <!-- ═══════════ 引用关系图谱弹窗 ═══════════ -->
  <el-dialog v-model="showCitationDialog" title="标准引用关系图谱" width="700px">
    <div v-if="citationLoading" style="text-align:center;padding:30px;">加载中...</div>
    <div v-else-if="citationData.nodes.length === 0" style="text-align:center;padding:30px;color:#999;">暂无引用数据</div>
    <div v-else>
      <div style="margin-bottom:8px;color:#909399;font-size:13px;">
        📊 {{ citationData.nodes.filter(n=>n.is_source).length }} 份库内标准，
        🔗 {{ citationData.edges.length }} 条引用关系，
        📖 {{ citationData.nodes.filter(n=>!n.is_source).length }} 份外部引用标准
      </div>
      <el-table :data="citationData.edges" size="small" max-height="400" stripe>
        <el-table-column label="引用方" min-width="180">
          <template #default="{ row }">
            {{ citationData.nodes.find(n=>n.id===row.source)?.label || row.source }}
          </template>
        </el-table-column>
        <el-table-column label="关系" width="60" align="center">
          <template #default><span style="color:#409eff;">→ 引用</span></template>
        </el-table-column>
        <el-table-column label="被引用标准" min-width="150">
          <template #default="{ row }">
            <el-tag size="small" :type="row.target.startsWith('ext:') ? 'warning' : 'success'">
              {{ row.label }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup>
import { onMounted, reactive, ref, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Upload, Search, User, Lock } from '@element-plus/icons-vue'
import { askQuestion, askStream, generateChunks, getDocuments, uploadDocument, analyzeDocument, getDocumentStats, searchDocuments, deleteDocument, createAnnotation, getClauses, draftCheck, getCitationGraph, login, register } from './services/api'
import { marked } from 'marked'
import * as echarts from 'echarts'

// ── 视图 ──
const activeView = ref('qa')

// ── 登录 ──
const loggedIn = ref(!!localStorage.getItem('token'))
const currentUser = ref(localStorage.getItem('username') || '')
const currentRole = ref(localStorage.getItem('role') || 'viewer')
const loginLoading = ref(false)
const loginError = ref('')
const loginMode = ref('login')
const loginForm = reactive({ username: '', password: '', confirm: '' })

function handleAuth() {
  if (loginMode.value === 'login') doLogin()
  else doRegister()
}

async function doLogin() {
  if (!loginForm.username || !loginForm.password) { loginError.value = '请输入用户名和密码'; return }
  loginLoading.value = true; loginError.value = ''
  try {
    const res = await login({ username: loginForm.username, password: loginForm.password })
    const data = res.data
    localStorage.setItem('token', data.token)
    localStorage.setItem('username', data.username)
    localStorage.setItem('role', data.role)
    loggedIn.value = true; currentUser.value = data.username; currentRole.value = data.role
    loadAllDocuments()
  } catch (e) {
    loginError.value = e?.response?.data?.detail || '登录失败'
  } finally { loginLoading.value = false }
}

async function doRegister() {
  if (!loginForm.username) { loginError.value = '请输入用户名'; return }
  if (loginForm.username.length < 2) { loginError.value = '用户名至少2位'; return }
  if (!loginForm.password) { loginError.value = '请输入密码'; return }
  if (loginForm.password.length < 6) { loginError.value = '密码至少6位'; return }
  if (loginForm.password !== loginForm.confirm) { loginError.value = '两次密码不一致'; return }
  loginLoading.value = true; loginError.value = ''
  try {
    const res = await register({ username: loginForm.username, password: loginForm.password })
    const data = res.data
    localStorage.setItem('token', data.token)
    localStorage.setItem('username', data.username)
    localStorage.setItem('role', data.role)
    loggedIn.value = true; currentUser.value = data.username; currentRole.value = data.role
    loadAllDocuments()
  } catch (e) {
    loginError.value = e?.response?.data?.detail || '注册失败'
  } finally { loginLoading.value = false }
}

function doLogout() {
  localStorage.removeItem('token'); localStorage.removeItem('username'); localStorage.removeItem('role')
  loggedIn.value = false; currentUser.value = ''
  chatHistory.value = []
}

// 恢复登录态（api 拦截器自动从 localStorage 读 token）
if (loggedIn.value) {
  currentRole.value = localStorage.getItem('role') || 'viewer'
}

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
const askDocIds = ref([])

// ── 切片 ──
const chunkLoadingId = ref(null)

// ── 弹窗 ──
const showDetailDialog = ref(false)
const detailDoc = ref(null)
const showAnalysisDialog = ref(false)
const showCitationDialog = ref(false)
const citationLoading = ref(false)
const citationData = ref({ nodes: [], edges: [] })

// ── 标注 ──
const showAnnotationDialog = ref(false)
const annotationText = ref('')
const annotationRef = ref(null)
const annotationSaving = ref(false)

function startAnnotation(ref) {
  annotationRef.value = ref
  annotationText.value = ''
  showAnnotationDialog.value = true
}

// ── 起草辅助 ──
const showDraftDialog = ref(false)
const draftClauses = ref([])
const draftLoading = ref(false)
const draftResult = ref('')
const draftDocId = ref(null)

async function openDraftCheck(row) {
  showDraftDialog.value = true; draftLoading.value = true; draftResult.value = ''; draftClauses.value = []
  draftDocId.value = row.id
  try {
    const res = await getClauses(row.id)
    draftClauses.value = res.data.clauses || []
  } catch { ElMessage.error('加载条款失败，请先生成切片') }
  finally { draftLoading.value = false }
}

async function checkDraftClause(cl) {
  draftResult.value = '检查中...'
  try {
    const res = await draftCheck(draftDocId.value, {
      question: `草案第 ${cl.section_number} 条（${cl.section_path}）与现行标准中的相关要求是否冲突？如有，请列出差异和修改建议`,
      limit: 5,
    })
    draftResult.value = res.data.answer || '未找到相关对比信息'
  } catch { draftResult.value = '检查失败，请重试' }
}

async function saveAnnotation() {
  if (!annotationText.value.trim()) { ElMessage.warning('请输入标注内容'); return }
  annotationSaving.value = true
  try {
    await createAnnotation({
      document_id: annotationRef.value.document_id,
      chunk_id: annotationRef.value.chunk_id || null,
      content: annotationText.value.trim(),
    })
    ElMessage.success('标注已保存')
    showAnnotationDialog.value = false
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally { annotationSaving.value = false }
}
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

const backfilling = ref(false)

// ── 图表 ──
const typeChartRef = ref(null)
const industryChartRef = ref(null)
let typeChart = null
let industryChart = null

// ── Markdown 渲染 ──
function renderMarkdown(text) {
  if (!text) return ''
  return marked(text, { breaks: true, gfm: true })
}

// ═══════════ 方法 ═══════════

function switchView(view) {
  activeView.value = view
  if (view === 'docs') { loadDocuments() }
  if (view === 'qa') { loadAllDocuments() }
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
      const res = await searchDocuments(searchKeyword.value, docPage.value, docPageSize.value)
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
      const sr = await getDocumentStats()
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
    let allDocs = []
    let page = 1
    const pageSize = 100
    while (true) {
      const res = await getDocuments({ page, page_size: pageSize })
      const docs = res.data.documents || (Array.isArray(res.data) ? res.data : [])
      allDocs = allDocs.concat(docs)
      if (docs.length < pageSize) break
      page++
    }
    allDocuments.value = allDocs
  } catch (e) {
    console.error('[QA] 加载标准列表失败:', e)
    try {
      const res = await getDocuments({ page: 1, page_size: 100 })
      allDocuments.value = res.data?.documents || []
    } catch { allDocuments.value = [] }
  }
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
    const res = await analyzeDocument(row.id)
    analysisResult.value = res.data.analysis
    showAnalysisDialog.value = true
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '分析失败，请先生成切片') }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定要删除「${row.filename}」吗？此操作不可恢复。`, '确认删除', {
      type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消'
    })
    await deleteDocument(row.id)
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
    const payload = { question: q, limit: limit.value, document_ids: askDocIds.value.length ? askDocIds.value : null }
    for await (const event of askStream(payload)) {
      if (event.type === 'token') {
        aiMsg.content += event.content
        scrollToBottom()
      } else if (event.type === 'meta') {
        aiMsg.references = event.references || []
        aiMsg.followUps = event.follow_up_questions || []
        aiMsg.recommendations = event.recommendations || null
        aiMsg.isComparison = event.is_comparison || false
        aiMsg.comparisonCount = event.comparison_count || 0
        aiMsg.refsCount = (event.references || []).length
        if (event.auto_matched_document) {
          askDocIds.value = [event.auto_matched_document.document_id]
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
    aiMsg.isError = true
  } finally {
    aiMsg.streaming = false
    asking.value = false
    scrollToBottom()
  }
}

// ── 追问/重试/清空 ──
function clickFollowUp(text) {
  question.value = text
  submitAsk()
}

function retryAsk(msg) {
  // 找到该消息在历史中的位置，获取上一个用户问题重试
  const idx = chatHistory.value.indexOf(msg)
  if (idx > 0) {
    const userMsg = chatHistory.value[idx - 1]
    if (userMsg.role === 'user') {
      // 移除该 AI 消息
      chatHistory.value.splice(idx, 1)
      question.value = userMsg.content
      setTimeout(() => submitAsk(), 100)
    }
  }
}

async function showCitationGraph() {
  showCitationDialog.value = true
  citationLoading.value = true
  try {
    const res = await getCitationGraph()
    citationData.value = res.data.graph || { nodes: [], edges: [] }
  } catch {
    ElMessage.error('加载引用关系失败')
  } finally {
    citationLoading.value = false
  }
}

function clearChat() {
  chatHistory.value = []
  ElMessage.success('对话已清空')
}

function selectRecommendedDoc(rec) {
  if (!askDocIds.value.includes(rec.document_id)) {
    askDocIds.value = [...askDocIds.value, rec.document_id]
  }
  ElMessage.success('已添加标准: ' + rec.filename)
}

function groupedRefs(refs) {
  const groups = {}
  for (const r of refs) {
    const key = r.document_id || 0
    if (!groups[key]) groups[key] = { filename: r.filename || '未知标准', refs: [] }
    groups[key].refs.push(r)
  }
  return Object.values(groups)
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
  getDocumentStats().then(sr => {
    statsData.value = sr.data
    nextTick(() => renderCharts())
  }).catch(() => {})
})
</script>
