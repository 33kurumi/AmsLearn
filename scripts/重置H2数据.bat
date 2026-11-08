@echo off
chcp 936 >nul
setlocal
set "ROOT=%~dp0.."
echo ========================================
echo 重置本地演示数据
echo ========================================
echo 将删除：
echo   business-service\data\student-project*.db   （H2 用户/知识点/记录/报告等）
echo   ai-service\data\knowledge_state.json          （知识库启停/上传状态）
echo 重启 Java 与 AI 服务后，演示账号与 67 个知识点会重新初始化。
echo 注意：必须先停止 Java / AI 服务，否则 H2 文件被占用会删除失败。
echo.
choice /c YN /m "确认重置演示数据"
if errorlevel 2 exit /b 0
echo.
if exist "%ROOT%\business-service\data\student-project.mv.db" (
  del /q "%ROOT%\business-service\data\student-project.mv.db"
  if errorlevel 1 (echo [失败] H2 数据库被占用，请先停止 Java 服务。 & pause & exit /b 1)
)
if exist "%ROOT%\business-service\data\student-project.trace.db" del /q "%ROOT%\business-service\data\student-project.trace.db"
if exist "%ROOT%\ai-service\data\knowledge_state.json" (
  del /q "%ROOT%\ai-service\data\knowledge_state.json"
)
echo.
echo 已重置。请重新运行 scripts\启动全部服务.bat。
pause
endlocal