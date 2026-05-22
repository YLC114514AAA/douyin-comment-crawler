@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   抖音评论区爬虫 — 一键安装依赖
echo ========================================
echo.
echo [1/4] 安装 Python 依赖...
pip install playwright customtkinter CTkMessagebox httpx PyExecJS cookiesparser -q
echo   完成！
echo.
echo [2/4] 安装 Chromium 浏览器内核（~150MB，首次较慢）...
python -m playwright install chromium
echo   完成！
echo.
echo [3/4] 安装 Node.js（用于签名计算）...
pip install nodejs-bin -q
echo   完成！
echo.
echo [4/4] 验证...
python -c "import customtkinter; import httpx; import execjs; print('所有依赖 OK')"
echo.
echo ========================================
echo   安装完成！双击 gui启动.bat 运行
echo ========================================
pause
