/**
 * src/utils/vision.js —— 图片答疑（v1.3）前端工具
 * 约束：不新增依赖，压缩使用原生 canvas。
 * - 允许 PNG / JPEG / WebP / GIF，单张 ≤ 5MB（与 AI/Java 侧校验一致）
 * - 压缩策略：最长边 ≤ 1600px，统一导出 JPEG（质量 0.85），白底避免透明区域变黑
 * - 纯函数（validateImageFile / compressionPlan / formatFileSize）便于单元测试
 */

export const MAX_IMAGE_EDGE = 1600
export const JPEG_QUALITY = 0.85
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024

export const ACCEPT_MIME = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
export const ACCEPT_ATTR = ACCEPT_MIME.join(',')

const EXT_MIME = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  gif: 'image/gif',
}

/** 文件大小 → 人类可读 */
export function formatFileSize(bytes) {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  if (value < 1024) return value + ' B'
  if (value < 1024 * 1024) return (value / 1024).toFixed(1) + ' KB'
  return (value / (1024 * 1024)).toFixed(2) + ' MB'
}

/** 由 MIME 或扩展名推断图片类型；非图片返回空字符串 */
export function imageMime(file) {
  if (!file) return ''
  const type = String(file.type || '').toLowerCase()
  if (ACCEPT_MIME.includes(type)) return type
  const name = String(file.name || '')
  const match = /\.([a-z0-9]+)$/i.exec(name)
  if (match) {
    const guessed = EXT_MIME[match[1].toLowerCase()]
    if (guessed) return guessed
  }
  return ''
}

/** 上传前校验：类型 + 大小。返回 {ok, message} */
export function validateImageFile(file, maxBytes = MAX_IMAGE_BYTES) {
  if (!file) return { ok: false, message: '请选择一张题目图片。' }
  if (!imageMime(file)) {
    return { ok: false, message: '仅支持 PNG / JPEG / WebP / GIF 格式的图片。' }
  }
  const size = Number(file.size) || 0
  if (size <= 0) return { ok: false, message: '图片内容为空，请重新选择。' }
  if (size > maxBytes) {
    return {
      ok: false,
      message: '图片大小 ' + formatFileSize(size) + ' 超过 ' + formatFileSize(maxBytes) + '，请裁剪后再上传。',
    }
  }
  return { ok: true, message: '' }
}

/** 计算压缩后的目标尺寸（最长边 ≤ maxEdge，保持比例，不放大） */
export function compressionPlan(width, height, maxEdge = MAX_IMAGE_EDGE) {
  const w = Number(width) || 0
  const h = Number(height) || 0
  if (w <= 0 || h <= 0) {
    return { scale: 1, targetWidth: 0, targetHeight: 0, needsResize: false, valid: false }
  }
  const edge = Number(maxEdge) > 0 ? Number(maxEdge) : MAX_IMAGE_EDGE
  const scale = Math.min(1, edge / Math.max(w, h))
  return {
    scale,
    targetWidth: Math.max(1, Math.round(w * scale)),
    targetHeight: Math.max(1, Math.round(h * scale)),
    needsResize: scale < 1,
    valid: true,
  }
}

async function decodeImage(file) {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file, { imageOrientation: 'from-image' })
    } catch {
      /* 部分浏览器不支持该 option，回退 <img> */
    }
  }
  const url = URL.createObjectURL(file)
  try {
    const image = await new Promise((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = () => reject(new Error('图片解析失败，请换一张图片或直接输入文字。'))
      el.src = url
    })
    return image
  } finally {
    URL.revokeObjectURL(url)
  }
}

/**
 * 压缩图片：最长边 ≤ 1600px、JPEG q=0.85。
 * 返回 File（name 改为 .jpg，type=image/jpeg）。
 */
export async function compressImageFile(file, { maxEdge = MAX_IMAGE_EDGE, quality = JPEG_QUALITY } = {}) {
  if (typeof document === 'undefined') {
    throw new Error('当前环境不支持图片压缩，请直接输入文字。')
  }
  const source = await decodeImage(file)
  const width = source.width || source.naturalWidth || 0
  const height = source.height || source.naturalHeight || 0
  const plan = compressionPlan(width, height, maxEdge)
  if (!plan.valid) {
    if (source.close) source.close()
    throw new Error('无法读取图片尺寸，请换一张图片或直接输入文字。')
  }
  const canvas = document.createElement('canvas')
  canvas.width = plan.targetWidth
  canvas.height = plan.targetHeight
  const context = canvas.getContext('2d')
  if (!context) {
    if (source.close) source.close()
    throw new Error('当前浏览器不支持 canvas 压缩，请直接输入文字。')
  }
  // JPEG 无透明通道：先铺白底，避免 PNG 透明区域显示为黑块
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.drawImage(source, 0, 0, plan.targetWidth, plan.targetHeight)
  if (source.close) source.close()

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
  if (!blob) {
    throw new Error('图片压缩失败，请重试或直接输入文字。')
  }
  const baseName = String(file.name || 'image').replace(/\.[^.]+$/, '') || 'image'
  return new File([blob], baseName + '.jpg', { type: 'image/jpeg', lastModified: Date.now() })
}

export default {
  MAX_IMAGE_EDGE,
  JPEG_QUALITY,
  MAX_IMAGE_BYTES,
  ACCEPT_MIME,
  ACCEPT_ATTR,
  formatFileSize,
  imageMime,
  validateImageFile,
  compressionPlan,
  compressImageFile,
}
