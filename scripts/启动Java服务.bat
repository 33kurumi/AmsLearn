@echo off
setlocal
chcp 936 >nul
cd /d "%~dp0..\business-service"

set "JAVA_EXE="
for /f "delims=" %%J in ('where java 2^>nul') do if not defined JAVA_EXE set "JAVA_EXE=%%J"
if not defined JAVA_EXE goto no_java

for /f "tokens=3" %%V in ('java -version 2^>^&1 ^| findstr /i "version"') do set "JAVA_VERSION=%%~V"
for /f "tokens=1 delims=." %%M in ("%JAVA_VERSION%") do set "JAVA_MAJOR=%%M"
if "%JAVA_MAJOR%"=="1" for /f "tokens=2 delims=." %%M in ("%JAVA_VERSION%") do set "JAVA_MAJOR=%%M"
if not defined JAVA_MAJOR goto no_java
if %JAVA_MAJOR% LSS 17 goto old_java

for %%D in ("%JAVA_EXE%") do set "JAVA_BIN=%%~dpD"
for %%D in ("%JAVA_BIN%..") do set "JAVA_HOME=%%~fD"
echo 使用 Java %JAVA_VERSION%，JAVA_HOME=%JAVA_HOME%
set "MAVEN_OPTS=-Dfile.encoding=UTF-8"

netstat -ano | findstr /r /c:":8080 .*LISTENING" >nul && (
  echo [错误] 端口 8080 已被占用，请先运行 scripts\停止全部服务.bat。
  pause
  exit /b 1
)

echo Java 业务服务启动中：健康检查 http://localhost:8080/api/health  H2 控制台 http://localhost:8080/h2-console
call mvnw.cmd spring-boot:run
if errorlevel 1 (
  echo Java 服务启动失败，请检查 JDK 版本、8080 端口和 Maven 依赖下载。
)
pause
goto end

:no_java
echo 没有找到可用的 Java，请先安装 JDK 17 并配置 JAVA_HOME。
pause
goto end

:old_java
echo 当前 Java 版本为 %JAVA_VERSION%，本项目要求 JDK 17 或更高版本。
pause

:end
endlocal