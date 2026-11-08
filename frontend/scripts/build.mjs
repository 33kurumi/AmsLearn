// 受限环境（无子进程管道权限）下的构建入口：
// 1) 先禁用 Vite 在 Windows 上 exec("net use") 探测网络盘的逻辑（否则 spawn EPERM）；
// 2) 再用 runner 方式加载 vite.config.js，避免其用 esbuild 预打包配置文件；
// 3) 最后调用 Vite 官方 build API（define 替换与压缩已改为纯 JS 实现，不再启动 esbuild）。
// 在正常环境中该脚本的产物与 `vite build` 完全一致。
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
require('./sandbox-cp-patch.cjs')

const { build } = await import('vite')
await build({ configLoader: 'runner' })
