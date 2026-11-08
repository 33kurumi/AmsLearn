// 受限环境（无子进程管道权限）下的开发服务器入口：
// 1) 先禁用 Vite 在 Windows 上 exec("net use") 探测网络盘的逻辑（否则 spawn EPERM）；
// 2) 用 runner 方式加载 vite.config.js，避免 esbuild 预打包配置文件；
// 3) 启动官方 createServer（预构建已在 vite.config.js 中关闭，不再启动 esbuild）。
// 用法：npm run dev -- --port 5174（npm 可能吞掉 --port，故裸数字参数也识别为端口）
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
require('./sandbox-cp-patch.cjs')

const args = process.argv.slice(2)
let port = 5173
let host = undefined
for (let i = 0; i < args.length; i += 1) {
  const arg = args[i]
  if (/^\d+$/.test(arg)) port = Number(arg)
  else if (arg === '--port' || arg === '-p') port = Number(args[i + 1])
  else if (arg.startsWith('--port=')) port = Number(arg.split('=')[1])
  else if (arg === '--host') host = args[i + 1] || true
  else if (arg.startsWith('--host=')) host = arg.split('=')[1]
}

const { createServer } = await import('vite')
const server = await createServer({
  configLoader: 'runner',
  server: host ? { port, host } : { port },
})
await server.listen()
server.printUrls()
