<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, assetUrl } from './api'

const modules = [
  { id: 'character', index: 1, name: 'AI 角色生成', hint: '输入文字生成 512x512 角色三视图' },
  { id: 'video', index: 2, name: 'AI 视频生成', hint: '选择角色图作为参考输入' },
  { id: 'motion', index: 3, name: '动作捕捉', hint: '选择视频结果提取动作数据' },
  { id: 'facial', index: 4, name: '表情捕捉', hint: '选择上游产物提取表情曲线' },
]

const activeModule = ref('character')
const loading = ref(false)
const error = ref('')
const backendStatus = ref('checking')
const assets = ref([])

// 缓存已加载的 JSON 文本，避免重复请求；key 为 asset.id
const jsonPreviews = reactive({})

// 每个模块的历史任务列表（按时间倒序，由后端返回）
const jobsHistory = reactive({
  character: [],
  video: [],
  motion: [],
  facial: [],
})

// 每个模块当前在预览面板中展示的任务 id；为空时展示该模块最近一次任务
const selectedJobIds = reactive({
  character: '',
  video: '',
  motion: '',
  facial: '',
})

const jobs = reactive({
  character: null,
  video: null,
  motion: null,
  facial: null,
})

const forms = reactive({
  character: {
    prompt: '东方废土少年机械术士，机械右臂，轻量级战斗装备，适合 Unity 实时渲染',
    model: 'qwen',
  },
  video: {
    prompt: '角色站立待机，轻微转身，机械右臂发出微光，镜头稳定，5 秒短片',
    selectedAssetId: '',
    model: 'qwen',
  },
  motion: {
    selectedAssetId: '',
    model: 'qwen',
  },
  facial: {
    selectedAssetId: '',
    model: 'qwen',
  },
})

// 各模块可选的模型列表，目前仅做 UI 预留，不传给后端
const modelOptions = [
  { value: 'qwen', label: '千问 (Qwen)' },
  { value: 'doubao', label: '豆包 (Doubao)' },
  { value: 'gpt', label: 'GPT' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'claude', label: 'Claude' },
]

const currentModule = computed(() => modules.find((item) => item.id === activeModule.value))
// 当前模块的历史任务列表（仅展示已成功的任务，失败任务没有可看的输出）
const currentJobHistory = computed(() =>
  (jobsHistory[activeModule.value] || []).filter((job) => job.status === 'succeeded'),
)
// 用户选中的历史任务；为空时优先回退到本会话最近一次任务，再回退到持久化历史的最新一条
const currentJob = computed(() => {
  const selectedId = selectedJobIds[activeModule.value]
  if (selectedId) {
    return currentJobHistory.value.find((job) => job.id === selectedId) || null
  }
  // 本会话刚跑过的任务优先（包含运行中/失败的状态变化，体验最实时）
  const sessionJob = jobs[activeModule.value]
  if (sessionJob) return sessionJob
  // 没有会话任务时，自动展示该模块持久化历史中最近一次成功任务，避免空白
  return currentJobHistory.value[0] || null
})
const characterAssets = computed(() => filterAssets('character').filter((asset) => asset.type === 'image'))
const videoAssets = computed(() => filterAssets('video').filter((asset) => asset.type === 'video'))
const motionAssets = computed(() => filterAssets('motion').filter((asset) => asset.type === 'motion'))
// 视频模块当前选中的角色图片资产，用于在表单旁展示缩略图
const selectedCharacterAsset = computed(() =>
  characterAssets.value.find((asset) => asset.id === forms.video.selectedAssetId) || null,
)
const currentOutputs = computed(() => currentJob.value?.outputs || [])
const currentStatusText = computed(() => formatJobStatus(currentJob.value))

// 文件名去扩展名，用于把同名图片与 JSON 配对（character_image_1.png ↔ character_image_1.json）
function stemOf(name) {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? name : name.slice(0, dot)
}

// 把当前输出按"图片 + 同名 JSON"配对成预览项，剩余资源仍单独展示
const previewItems = computed(() => {
  const outputs = currentOutputs.value
  // 先按 stem 建立 JSON 索引
  const jsonByStem = new Map()
  for (const asset of outputs) {
    if (asset.format === 'json') {
      jsonByStem.set(stemOf(asset.name), asset)
    }
  }
  const usedJsonIds = new Set()
  const items = []
  // 第一轮：图片/预览类资源尝试配对同名 JSON
  for (const asset of outputs) {
    if (asset.format === 'json') continue
    const kind = previewKind(asset)
    if (kind === 'image') {
      const paired = jsonByStem.get(stemOf(asset.name))
      if (paired) {
        usedJsonIds.add(paired.id)
        items.push({ kind: 'paired', primary: asset, json: paired })
        continue
      }
    }
    items.push({ kind: 'single', asset })
  }
  // 第二轮：未被配对的 JSON 单独展示，避免遗漏
  for (const asset of outputs) {
    if (asset.format === 'json' && !usedJsonIds.has(asset.id)) {
      items.push({ kind: 'single', asset })
    }
  }
  return items
})

function filterAssets(moduleId) {
  return assets.value.filter((asset) => asset.module === moduleId)
}

function chooseModule(moduleId) {
  activeModule.value = moduleId
  error.value = ''
  // 切换模块时刷新一次该模块的历史任务，保证下拉框是最新的
  refreshJobsHistory(moduleId)
}

async function refreshAssets() {
  assets.value = await api.assets()
}

// 拉取指定模块的任务历史，写入 jobsHistory；失败时静默保留旧值
async function refreshJobsHistory(moduleId) {
  try {
    const response = await api.listJobs(moduleId)
    jobsHistory[moduleId] = response.jobs || []
  } catch (err) {
    // 拉取失败不阻塞主流程，只在控制台留痕
    console.warn(`加载 ${moduleId} 模块历史任务失败：`, err.message)
  }
}

function onSelectHistoryJob(event) {
  // 下拉框切换历史任务：空字符串代表回到最近一次任务
  selectedJobIds[activeModule.value] = event.target.value
}

async function checkBackend() {
  try {
    await api.health()
    backendStatus.value = 'online'
    // 预加载资产与各模块历史任务，便于切换模块时立刻看到下拉
    await refreshAssets()
    await Promise.all(modules.map((mod) => refreshJobsHistory(mod.id)))
  } catch (err) {
    backendStatus.value = 'offline'
    error.value = `后端不可用：${err.message}`
  }
}

async function runCharacter() {
  await runJob('character', () =>
    api.createCharacterJob({
      prompt: forms.character.prompt,
      generate_image: true,
      generate_multiview: false,
      generate_3d: false,
      image_provider: 'qwen-image-2.0-pro',
      params: {
        negative_prompt: '低分辨率，低画质，肢体畸形，手指畸形，文字模糊，水印',
        prompt_extend: true,
        watermark: false,
        n: 1,
      },
    }),
  )
}

async function runVideo() {
  await runJob('video', () =>
    api.createVideoJob({
      prompt: forms.video.prompt,
      character_asset_ids: forms.video.selectedAssetId ? [forms.video.selectedAssetId] : [],
      duration_seconds: 5,
      fps: 24,
      resolution: '720P',
      provider: 'wan2.7-i2v-2026-04-25',
      params: {
        prompt_extend: true,
        watermark: false,
        poll_interval_seconds: 15,
        max_wait_seconds: 900,
      },
    }),
  )
}

async function runMotion() {
  if (!forms.motion.selectedAssetId) {
    error.value = '请先选择 AI 视频生成模块的输出作为输入。'
    return
  }
  // 默认走本地 MediaPipe Pose 动捕：输出关键点 JSON + 骨架叠加预览 mp4
  // 如需千面云服务，把 provider 改成 'qianmian_motion'
  await runJob('motion', () =>
    api.createMotionJob({
      input_video_asset_id: forms.motion.selectedAssetId,
      provider: 'mediapipe_motion',
      target_skeleton: 'humanoid',
      output_formats: ['json', 'mp4'],
      params: {
        min_pose_detection_confidence: 0.5,
        min_pose_presence_confidence: 0.5,
        min_tracking_confidence: 0.5,
        num_poses: 1,
      },
    }),
  )
}

async function runFacial() {
  if (!forms.facial.selectedAssetId) {
    error.value = '请先选择动作捕捉模块的输出作为输入。'
    return
  }
  await runJob('facial', () =>
    api.createFacialJob({
      input_asset_id: forms.facial.selectedAssetId,
      provider: 'mock_facial',
      output_standard: 'arkit_52',
      include_head_pose: true,
      output_formats: ['json', 'csv'],
      params: {
        fps: 30,
        smooth: true,
      },
    }),
  )
}

async function runJob(moduleId, action) {
  loading.value = true
  error.value = ''
  try {
    // 后端任务接口会把业务失败写入 job.status，因此这里需要显式判断任务状态。
    const job = await action()
    jobs[moduleId] = job
    if (job.status === 'failed') {
      error.value = formatJobError(job.error)
      return
    }
    // 新任务跑成功后清空历史选择，让预览自动回到最新一次任务
    selectedJobIds[moduleId] = ''
    await Promise.all([refreshAssets(), refreshJobsHistory(moduleId)])
    selectNewOutputsForNextStep(moduleId)
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function selectNewOutputsForNextStep(moduleId) {
  const outputs = jobs[moduleId]?.outputs || []
  const firstOutput = outputs.find((asset) => ['image', 'video', 'motion', 'facial'].includes(asset.type))
  if (!firstOutput) return

  if (moduleId === 'character') forms.video.selectedAssetId = firstOutput.id
  if (moduleId === 'video') forms.motion.selectedAssetId = firstOutput.id
  if (moduleId === 'motion') forms.facial.selectedAssetId = firstOutput.id
}

function previewKind(asset) {
  if (asset.type === 'image' || asset.type === 'preview') return 'image'
  if (asset.type === 'video') return 'video'
  // JSON 单独走文本展示分支，便于读取并美化显示
  if (asset.format === 'json') return 'json'
  if (asset.format === 'csv' || asset.format === 'bvh') return 'text'
  return 'file'
}

// 拉取 JSON 内容并缓存，预览面板会响应式更新
async function loadJsonPreview(asset) {
  if (jsonPreviews[asset.id]) return
  try {
    const response = await fetch(assetUrl(asset.id))
    if (!response.ok) {
      jsonPreviews[asset.id] = `加载失败：HTTP ${response.status}`
      return
    }
    const text = await response.text()
    try {
      // 尝试格式化为缩进 JSON，提升可读性
      jsonPreviews[asset.id] = JSON.stringify(JSON.parse(text), null, 2)
    } catch {
      // 不是合法 JSON 时也展示原始文本，避免空白
      jsonPreviews[asset.id] = text
    }
  } catch (err) {
    jsonPreviews[asset.id] = `加载失败：${err.message}`
  }
}

// 当前模块的输出列表变化时，预加载所有 JSON 内容
watch(
  () => currentOutputs.value,
  (outputs) => {
    for (const asset of outputs) {
      if (previewKind(asset) === 'json') {
        loadJsonPreview(asset)
      }
    }
  },
  { immediate: true },
)

function formatJobStatus(job) {
  if (!job) return '未创建任务'
  const statusMap = {
    pending: '等待中',
    running: '执行中',
    succeeded: '已完成',
    failed: '失败',
  }
  return statusMap[job.status] || job.status
}

function formatJobError(message) {
  if (!message) return '任务执行失败，请查看后端日志。'
  if (message.includes('Missing DASHSCOPE_API_KEY')) {
    return '缺少 DASHSCOPE_API_KEY，请在 backend/.env 或启动后端前的 shell 环境中配置后再生成角色图片。'
  }
  return message
}

// 历史任务下拉的显示文案：时间 + 输出数 + 简短任务 id 尾巴
function formatJobLabel(job) {
  const created = job.created_at ? new Date(job.created_at) : null
  const timeText = created
    ? `${created.getFullYear()}/${String(created.getMonth() + 1).padStart(2, '0')}/${String(created.getDate()).padStart(2, '0')} ${String(created.getHours()).padStart(2, '0')}:${String(created.getMinutes()).padStart(2, '0')}`
    : '时间未知'
  const outputs = job.outputs?.length ?? 0
  const idTail = job.id ? job.id.slice(-6) : ''
  return `${timeText} · ${outputs} 个输出 · ${idTail}`
}

onMounted(checkBackend)
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">AI</div>
        <div>
          <h1>角色生产工具链</h1>
          <p :class="['status', backendStatus]">{{ backendStatus === 'online' ? '后端已连接' : backendStatus === 'offline' ? '后端未连接' : '检查后端中' }}</p>
        </div>
      </div>

      <nav class="module-nav" aria-label="模块导航">
        <button
          v-for="item in modules"
          :key="item.id"
          :class="['module-button', { active: item.id === activeModule }]"
          type="button"
          @click="chooseModule(item.id)"
        >
          <span class="step">{{ item.index }}</span>
          <span>
            <strong>{{ item.name }}</strong>
            <small>{{ item.hint }}</small>
          </span>
        </button>
      </nav>
    </aside>

    <main class="workspace">
      <header class="workspace-header">
        <div>
          <p class="eyebrow">模块 {{ currentModule.index }}</p>
          <h2>{{ currentModule.name }}</h2>
        </div>
        <button class="ghost-button" type="button" @click="refreshAssets">刷新资产</button>
      </header>

      <p v-if="error" class="error-message">{{ error }}</p>

      <section v-if="activeModule === 'character'" class="work-panel">
        <label class="field">
          <span>模型选择</span>
          <select v-model="forms.character.model">
            <option v-for="opt in modelOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>提示词</span>
          <textarea v-model="forms.character.prompt" rows="6" />
        </label>
        <p class="note">后端会强制追加人物全身和三视图要求。</p>
        <button class="primary-button" type="button" :disabled="loading" @click="runCharacter">
          {{ loading ? '生成中' : '生成角色' }}
        </button>
      </section>

      <section v-if="activeModule === 'video'" class="work-panel">
        <label class="field">
          <span>模型选择</span>
          <select v-model="forms.video.model">
            <option v-for="opt in modelOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>选择 AI 角色生成输出</span>
          <select v-model="forms.video.selectedAssetId">
            <option value="">不选择上游资产</option>
            <option v-for="asset in characterAssets" :key="asset.id" :value="asset.id">
              {{ asset.name }} · {{ asset.format }}
            </option>
          </select>
        </label>
        <!-- 选中角色图后展示缩略预览，方便确认参考图正确 -->
        <div v-if="selectedCharacterAsset" class="selected-asset-preview">
          <img :src="assetUrl(selectedCharacterAsset.id)" :alt="selectedCharacterAsset.name" />
          <div class="selected-asset-meta">
            <strong>{{ selectedCharacterAsset.name }}</strong>
            <span>{{ selectedCharacterAsset.type }} · {{ selectedCharacterAsset.format }}</span>
            <a :href="assetUrl(selectedCharacterAsset.id)" target="_blank" rel="noreferrer">查看原图</a>
          </div>
        </div>
        <label class="field">
          <span>提示词</span>
          <textarea v-model="forms.video.prompt" rows="5" />
        </label>
        <button class="primary-button" type="button" :disabled="loading" @click="runVideo">
          {{ loading ? '生成中' : '生成视频' }}
        </button>
      </section>

      <section v-if="activeModule === 'motion'" class="work-panel">
        <label class="field">
          <span>模型选择</span>
          <select v-model="forms.motion.model">
            <option v-for="opt in modelOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>选择 AI 视频生成输出</span>
          <select v-model="forms.motion.selectedAssetId">
            <option value="">请选择视频模块输出</option>
            <option v-for="asset in videoAssets" :key="asset.id" :value="asset.id">
              {{ asset.name }} · {{ asset.format }}
            </option>
          </select>
        </label>
        <button class="primary-button" type="button" :disabled="loading" @click="runMotion">
          {{ loading ? '处理中' : '生成动作捕捉数据' }}
        </button>
      </section>

      <section v-if="activeModule === 'facial'" class="work-panel">
        <label class="field">
          <span>模型选择</span>
          <select v-model="forms.facial.model">
            <option v-for="opt in modelOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>选择动作捕捉输出</span>
          <select v-model="forms.facial.selectedAssetId">
            <option value="">请选择动作捕捉模块输出</option>
            <option v-for="asset in motionAssets" :key="asset.id" :value="asset.id">
              {{ asset.name }} · {{ asset.format }}
            </option>
          </select>
        </label>
        <button class="primary-button" type="button" :disabled="loading" @click="runFacial">
          {{ loading ? '处理中' : '生成表情捕捉数据' }}
        </button>
      </section>

      <section class="preview-section">
        <div class="section-title">
          <h3>结果预览</h3>
          <div class="section-title-right">
            <!-- 历史任务下拉：默认显示最近一次，可选择任意成功任务回看 -->
            <label v-if="currentJobHistory.length" class="history-picker">
              <span>历史任务</span>
              <select
                :value="selectedJobIds[activeModule]"
                @change="onSelectHistoryJob"
              >
                <option value="">最近一次任务</option>
                <option v-for="job in currentJobHistory" :key="job.id" :value="job.id">
                  {{ formatJobLabel(job) }}
                </option>
              </select>
            </label>
            <span>{{ currentStatusText }} · {{ currentOutputs.length }} 个输出</span>
          </div>
        </div>

        <div v-if="currentJob" :class="['job-status', currentJob.status]">
          <strong>最近任务：{{ currentJob.id }}</strong>
          <span>{{ currentStatusText }}</span>
          <p v-if="currentJob.error">{{ formatJobError(currentJob.error) }}</p>
        </div>

        <div v-if="!currentOutputs.length" class="empty-preview">
          当前模块还没有生成结果。
        </div>

        <div v-else class="preview-grid">
          <template v-for="item in previewItems" :key="item.kind === 'paired' ? item.primary.id : item.asset.id">
            <!-- 图片 + 同名 JSON：左右并排，JSON 侧独立滚动 -->
            <article v-if="item.kind === 'paired'" class="asset-item asset-item-paired">
              <div class="paired-body">
                <div class="paired-image">
                  <div class="asset-preview">
                    <img :src="assetUrl(item.primary.id)" :alt="item.primary.name" />
                  </div>
                  <div class="asset-meta">
                    <strong>{{ item.primary.name }}</strong>
                    <span>{{ item.primary.type }} · {{ item.primary.format }}</span>
                    <a :href="assetUrl(item.primary.id)" target="_blank" rel="noreferrer">打开文件</a>
                  </div>
                </div>
                <div class="paired-json">
                  <header class="paired-json-header">
                    <strong>{{ item.json.name }}</strong>
                    <a :href="assetUrl(item.json.id)" target="_blank" rel="noreferrer">打开文件</a>
                  </header>
                  <pre class="json-preview json-preview-scroll">{{ jsonPreviews[item.json.id] ?? '加载中…' }}</pre>
                </div>
              </div>
            </article>

            <!-- 未配对的资源（视频、单独 JSON、其它文本/文件等） -->
            <article v-else :class="['asset-item', { 'asset-item-json': previewKind(item.asset) === 'json' }]">
              <div class="asset-preview">
                <img v-if="previewKind(item.asset) === 'image'" :src="assetUrl(item.asset.id)" :alt="item.asset.name" />
                <video v-else-if="previewKind(item.asset) === 'video'" :src="assetUrl(item.asset.id)" controls />
                <pre v-else-if="previewKind(item.asset) === 'json'" class="json-preview json-preview-scroll">{{ jsonPreviews[item.asset.id] ?? '加载中…' }}</pre>
                <iframe v-else-if="previewKind(item.asset) === 'text'" :src="assetUrl(item.asset.id)" title="文本预览" />
                <div v-else class="file-fallback">{{ item.asset.format.toUpperCase() }}</div>
              </div>
              <div class="asset-meta">
                <strong>{{ item.asset.name }}</strong>
                <span>{{ item.asset.type }} · {{ item.asset.format }}</span>
                <a :href="assetUrl(item.asset.id)" target="_blank" rel="noreferrer">打开文件</a>
              </div>
            </article>
          </template>
        </div>

        <!-- 3D 资产预览预留窗口：仅在角色生成模块显示，目前不接入任何数据 -->
        <div v-if="activeModule === 'character'" class="model3d-placeholder">
          <header class="model3d-placeholder-header">
            <strong>3D 资产预览</strong>
            <span>预留窗口</span>
          </header>
          <div class="model3d-placeholder-body">
            暂未生成 3D 资产，等待后续接入。
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
