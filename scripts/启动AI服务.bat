@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0.."
set "TMP=%~dp0..\.tmp"
set "TEMP=%~dp0..\.tmp"
if not exist ".tmp" mkdir ".tmp" >nul 2>nul
cd /d "%~dp0..\ai-service"

if not exist ".venv\Scripts\python.exe" (
  echo 未检测到 .venv，正在创建虚拟环境并安装依赖（首次约 1-3 分钟）...
  python -m venv .venv
  if errorlevel 1 (
    echo [错误] 虚拟环境创建失败，请确认已安装 Python 3.12 且加入 PATH。
    pause
    exit /b 1
  )
  rem --no-cache-dir：受限环境默认 pip 缓存在用户目录会被拒绝并表现为卡死
  rem TMP 已指向工作区，避免临时文件写入失败
  .venv\Scripts\python.exe -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  if errorlevel 1 (
    echo [提示] 镜像源安装失败，尝试默认源...
    .venv\Scripts\python.exe -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
  )
  if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络或使用课堂离线依赖。
    pause
    exit /b 1
  )
)

if not exist ".env" (
  echo [提示] 未找到 .env，将以 mock 模式运行（无需 DeepSeek key，可完整演示）。
  echo        需要真实大模型：复制 .env.example 为 .env，填写 DEEPSEEK_API_KEY，保持 AI_MODE=auto。
)

netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul && (
  echo [错误] 端口 8000 已被占用，请先运行 scripts\停止全部服务.bat。
  pause
  exit /b 1
)

echo AI 服务启动中：健康检查 http://localhost:8000/health  接口文档 http://localhost:8000/docs
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
endlocal