import { reactive } from 'vue'

/**
 * 极简全局 toast，配合 ToastHost.vue 使用。
 * 用法：toast.success('已保存') / toast.error(err.message) / toast.info('...')
 */
export const toastState = reactive({ items: [] })

let seed = 0
const MAX_ITEMS = 5

export function dismissToast(id) {
  const index = toastState.items.findIndex((item) => item.id === id)
  if (index >= 0) toastState.items.splice(index, 1)
}

export function toast(message, type = 'info', duration = 3200) {
  if (!message) return null
  const id = ++seed
  toastState.items.push({ id, message: String(message), type })
  while (toastState.items.length > MAX_ITEMS) toastState.items.shift()
  if (duration > 0) {
    setTimeout(() => dismissToast(id), duration)
  }
  return id
}

toast.success = (message, duration) => toast(message, 'success', duration)
toast.error = (message, duration = 4600) => toast(message, 'error', duration)
toast.info = (message, duration) => toast(message, 'info', duration)
toast.dismiss = dismissToast
