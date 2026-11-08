@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0..\frontend"

rem 把 npm 缓存固定在工作区内，避免沙箱环境 npm 缓存目录 EPERM 报错
set "npm_config_cache=%~dp0..\.npm-cache"

if not exist "node_modules" (
  echo 尚未安装前端依赖，正在执行 npm install（首次约 1-3 分钟）...
  call npm install
  if errorlevel 1 (
    echo [错误] 前端依赖安装失败，请查看上方 npm 报错并保留窗口。
    pause
    exit /b 1
  )
)

netstat -ano | findstr /r /c:":5173 .*LISTENING" >nul && (
  echo [错误] 端口 5173 已被占用，请先运行 scripts\停止全部服务.bat。
  pause
  exit /b 1
)

echo 前端启动中：http://localhost:5173 （演示账号 student1 / teacher1，密码 123456）
call npm run dev
pause
endlocal