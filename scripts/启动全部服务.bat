@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0.."
echo ========================================
echo AmsLearn 一键启动（AI - Java - 前端）
echo ========================================
echo 首次使用前请先执行 scripts\检查环境.bat 并安装依赖。
echo 启动顺序：AI 8000 -^> Java 8080 -^> 前端 5173，等待 5 秒后自动打开下一个窗口。
echo.
start "AI服务-8000" cmd /k call "%~dp0启动AI服务.bat"
timeout /t 5 /nobreak >nul
start "Java服务-8080" cmd /k call "%~dp0启动Java服务.bat"
timeout /t 5 /nobreak >nul
start "Vue前端-5173" cmd /k call "%~dp0启动Vue前端.bat"
echo.
echo 三个窗口已打开。健康检查地址：
echo   http://localhost:8000/health
echo   http://localhost:8080/api/health
echo   http://localhost:5173
echo 停止服务：双击 scripts\停止全部服务.bat
pause
endlocal