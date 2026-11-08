// 沙箱环境补丁：本机 DSH 沙箱禁止带管道 stdio 的子进程（spawn EPERM），
// Vite 在 Windows 上会执行 exec("net use") 探测网络盘，导致构建直接崩溃。
// 这里把 exec/execFile/execSync 降级为「直接回调错误」，net use 探测失败时 Vite 会安全回退。
const cp = require('node:child_process');
function noopExec(cmd, opts, cb) {
  const callback = typeof opts === 'function' ? opts : cb;
  if (typeof callback === 'function') {
    process.nextTick(() => callback(new Error('sandbox: child process spawn disabled')));
  }
  return { on() {}, kill() {}, unref() {} };
}
cp.exec = noopExec;
cp.execFile = noopExec;
cp.execSync = function () { throw new Error('sandbox: execSync disabled'); };
