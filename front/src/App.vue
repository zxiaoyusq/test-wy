<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
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

const jobs = reactive({
  character: null,
  video: null,
  motion: null,
  facial: null,
})

const forms = reactive({
  character: {
    prompt: '东方废土少年机械术士，机械右臂，轻量级战斗装备，适合 Unity 实时渲染',
  },
  video: {
    prompt: '角色站立待机，轻微转身，机械右臂发出微光，镜头稳定，5 秒短片',
    selectedAssetId: '',
  },
  motion: {
    selectedAssetId: '',
  },
  facial: {
    selectedAssetId: '',
  },
})

const currentModule = computed(() => modules.find((item) => item.id === activeModule.value))
const characterAssets = computed(() => filterAssets('character').filter((asset) => asset.type === 'image'))
const videoAssets = computed(() => filterAssets('video').filter((asset) => asset.type === 'video'))
const motionAssets = computed(() => filterAssets('motion').filter((asset) => asset.type === 'motion'))
const currentOutputs = computed(() => jobs[activeModule.value]?.outputs || [])

function filterAssets(moduleId) {
  return assets.value.filter((asset) => asset.module === moduleId)
}

function chooseModule(moduleId) {
  activeModule.value = moduleId
  error.value = ''
}

async function refreshAssets() {
  assets.value = await api.assets()
}

async function checkBackend() {
  try {
    await api.health()
    backendStatus.value = 'online'
    await refreshAssets()
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
  await runJob('motion', () =>
    api.createMotionJob({
      input_video_asset_id: forms.motion.selectedAssetId,
      provider: 'mock_motion',
      target_skeleton: 'humanoid',
      output_formats: ['json', 'bvh'],
      params: {
        fps: 30,
        coordinate_system: 'y_up',
        smooth: true,
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
    jobs[moduleId] = await action()
    await refreshAssets()
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
  if (asset.format === 'json' || asset.format === 'csv' || asset.format === 'bvh') return 'text'
  return 'file'
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
          <span>提示词</span>
          <textarea v-model="forms.character.prompt" rows="6" />
        </label>
        <p class="note">后端会强制追加人物全身和三视图要求。</p>
        <button class="primary-button" type="button" :disabled="loading" @click="runCharacter">
          {{ loading ? '生成中' : '生成角色图片' }}
        </button>
      </section>

      <section v-if="activeModule === 'video'" class="work-panel">
        <label class="field">
          <span>选择 AI 角色生成输出</span>
          <select v-model="forms.video.selectedAssetId">
            <option value="">不选择上游资产</option>
            <option v-for="asset in characterAssets" :key="asset.id" :value="asset.id">
              {{ asset.name }} · {{ asset.format }}
            </option>
          </select>
        </label>
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
          <span>{{ currentOutputs.length }} 个输出</span>
        </div>

        <div v-if="!currentOutputs.length" class="empty-preview">
          当前模块还没有生成结果。
        </div>

        <div v-else class="preview-grid">
          <article v-for="asset in currentOutputs" :key="asset.id" class="asset-item">
            <div class="asset-preview">
              <img v-if="previewKind(asset) === 'image'" :src="assetUrl(asset.id)" :alt="asset.name" />
              <video v-else-if="previewKind(asset) === 'video'" :src="assetUrl(asset.id)" controls />
              <iframe v-else-if="previewKind(asset) === 'text'" :src="assetUrl(asset.id)" title="文本预览" />
              <div v-else class="file-fallback">{{ asset.format.toUpperCase() }}</div>
            </div>
            <div class="asset-meta">
              <strong>{{ asset.name }}</strong>
              <span>{{ asset.type }} · {{ asset.format }}</span>
              <a :href="assetUrl(asset.id)" target="_blank" rel="noreferrer">打开文件</a>
            </div>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>
