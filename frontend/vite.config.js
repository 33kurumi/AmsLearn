import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// ---------------------------------------------------------------------------
// 定义替换插件（不依赖 esbuild）
// 说明：Vite 内置的 vite:define 插件在构建期通过 esbuild 服务完成 define 替换，
// 而 esbuild 需要以“带管道 stdio 的子进程”方式启动服务；在部分受限环境（如
// 本机 DSH 沙箱、企业安全策略、CI 受限容器）中该子进程会 spawn EPERM 导致构建
// 直接失败。这里用纯 JS 字符串替换完成同样的 define 注入，保证构建可以在
// 不启动任何子进程的情况下完成。正常环境下的产物与内置插件一致。
// ---------------------------------------------------------------------------
const VUE_DEFINES = [
  ['__VUE_OPTIONS_API__', 'true'],
  ['__VUE_PROD_DEVTOOLS__', 'false'],
  ['__VUE_PROD_HYDRATION_MISMATCH_DETAILS__', 'false'],
]

function envDefinePlugin(mode) {
  let isBuild = false
  let envVars = {}
  return {
    name: 'app:define-replacement',
    enforce: 'pre',
    configResolved(config) {
      isBuild = config.command === 'build'
      envVars = config.env || {}
      // 构建期移除内置 vite:define，避免其调用 esbuild 服务（受限环境会 spawn EPERM）
      if (isBuild) {
        for (let i = config.plugins.length - 1; i >= 0; i -= 1) {
          if (config.plugins[i].name === 'vite:define') config.plugins.splice(i, 1)
        }
      }
    },
    transform(code, id) {
      if (id.includes('/@vite/client') || id.includes('\@vite\client')) return null
      if (!/\.(m?js|vue|ts)$/.test(id.split('?')[0])) return null
      let next = code
      if (next.includes('process.env')) {
        next = next
          .replace(/globalThis\.process\.env\.NODE_ENV/g, JSON.stringify(mode))
          .replace(/global\.process\.env\.NODE_ENV/g, JSON.stringify(mode))
          .replace(/process\.env\.NODE_ENV/g, JSON.stringify(mode))
          .replace(/globalThis\.process\.env/g, '{}')
          .replace(/global\.process\.env/g, '{}')
          .replace(/process\.env/g, '{}')
      }
      for (const [key, value] of VUE_DEFINES) {
        if (next.includes(key)) next = next.split(key).join(value)
      }
      if (next.includes('import.meta.env')) {
        const fallback = { MODE: mode, DEV: !isBuild, PROD: isBuild, SSR: false, BASE_URL: '/' }
        next = next.replace(/import\.meta\.env\.([A-Za-z_$][\w$]*)/g, (raw, key) => {
          if (key in envVars) return JSON.stringify(envVars[key])
          if (key in fallback) return JSON.stringify(fallback[key])
          return 'undefined'
        })
        if (next.includes('import.meta.env')) {
          const envObject = { ...fallback, ...envVars }
          next = next.split('import.meta.env').join(JSON.stringify(envObject))
        }
      }
      if (next === code) return null
      return { code: next, map: null }
    },
  }
}

export default defineConfig(({ command, mode }) => ({
  plugins: [envDefinePlugin(mode), vue()],
  // 关闭 esbuild 转译与压缩：受限环境（无子进程权限）下 esbuild 无法启动服务。
  // 目标 esnext + 不压缩，产物仍是标准 ES Module，可直接由浏览器加载。
  esbuild: false,
  build: {
    target: 'esnext',
    minify: false,
    cssMinify: false,
    sourcemap: false,
  },
  // 开发态同样避免 esbuild 预构建（optimizeDeps 依赖 esbuild 服务）。
  optimizeDeps: {
    noDiscovery: true,
    include: [],
  },
  server: {
    port: 5173,
    strictPort: true,
    // 契约端口 5173；若把 VITE_API_BASE 配成相对路径（/api），则经由该代理转发到 Java 服务，
    // 可绕开浏览器跨域限制。默认前端直连 http://localhost:8080/api。
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
}))
