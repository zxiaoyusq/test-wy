const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = data?.detail || data?.message || response.statusText
    throw new Error(message)
  }
  return data
}

export function assetUrl(assetId) {
  return `${API_BASE_URL}/api/assets/${assetId}/file`
}

export const api = {
  health: () => request('/health'),
  assets: () => request('/api/assets'),
  // 拉取某个模块的历史任务列表（后端已按创建时间倒序返回）
  listJobs: (moduleId) => request(`/api/${moduleId}/jobs`),
  createCharacterJob: (payload) =>
    request('/api/character/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createVideoJob: (payload) =>
    request('/api/video/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createMotionJob: (payload) =>
    request('/api/motion/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createFacialJob: (payload) =>
    request('/api/facial/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

