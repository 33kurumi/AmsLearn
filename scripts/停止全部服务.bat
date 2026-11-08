@echo off
chcp 936 >nul
setlocal
echo 正在停止占用 8000 / 8080 / 5173 / 5174 端口的进程...
echo.
for %%P in (8000 8080 5173 5174) do (
  set "FOUND="
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
    if not defined FOUND (
      set "FOUND=1"
      echo   - 端口 %%P 的进程 PID %%A
      taskkill /PID %%A /T /F >nul 2>nul
    )
  )
)
echo.
echo 完成。若仍提示端口占用，请执行 netstat -ano ^| findstr :端口号 手工确认。
echo 数据库文件保留不动；需要清空演示数据请运行 scripts\重置H2数据.bat（先停止服务）。
pause
endlocal