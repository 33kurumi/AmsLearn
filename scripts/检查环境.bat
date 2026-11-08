@echo off
chcp 936 >nul
setlocal
echo ========================================
echo AmsLearn 环境检查（个性化学习导师）
echo ========================================
echo.
echo [1/6] Node.js（要求 20 以上，推荐 22 LTS）
node -v 2>nul || echo   [缺少] 未找到 Node.js，请安装 Node.js 22 并重新打开终端。
echo.
echo [2/6] npm（要求 10 以上）
call npm -v 2>nul || echo   [缺少] 未找到 npm，请随 Node.js 一起安装。
echo.
echo [3/6] JDK（要求 17）
java -version 2>&1
if errorlevel 1 echo   [缺少] 未找到 java，请安装 JDK 17 并配置 JAVA_HOME。
echo.
echo [4/6] Maven Wrapper（业务服务自带，无需单独安装 Maven）
call "%~dp0..\business-service\mvnw.cmd" -v 2>nul | findstr /i "Apache Maven"
if errorlevel 1 echo   [注意] Maven Wrapper 不可用：检查 business-service\.mvn 目录是否完整，或网络能否下载 Maven。
echo.
echo [5/6] Python（要求 3.11 或 3.12，推荐 3.12）
python --version 2>nul || echo   [缺少] 未找到 python，请安装 Python 3.12 并勾选 Add to PATH。
echo.
echo [6/6] 端口占用检查（8000 / 8080 / 5173 / 5174）
for %%P in (8000 8080 5173 5174) do (
  netstat -ano | findstr /r /c:":%%P .*LISTENING" >nul && echo   [占用] 端口 %%P 已被监听，请先运行 scripts\停止全部服务.bat。
)
echo.
echo [附加] AI 服务环境
if exist "%~dp0..\ai-service\.venv\Scripts\python.exe" (echo   venv 已创建) else (echo   [提示] 尚未创建 venv，见 docs\06-部署与运行手册.md 第 3 节。)
if exist "%~dp0..\ai-service\.env" (echo   .env 已存在，请确认 AI_MODE 与 DEEPSEEK_API_KEY) else (echo   [提示] 未找到 ai-service\.env：无 key 时保持 mock 模式即可完整演示。)
if exist "%~dp0..\frontend\node_modules" (echo   前端依赖已安装) else (echo   [提示] 前端未安装依赖，启动脚本会自动执行 npm install。)
echo.
echo 检查结束。环境安装与常见问题见 docs\06-部署与运行手册.md
pause
endlocal