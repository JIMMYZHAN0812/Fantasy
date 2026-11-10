@echo off
chcp 65001 >nul
echo ==========================================
echo   正在啟動 Fantasy 自動化更新程序...
echo ==========================================

:: 切換到專案資料夾
cd /d C:\Users\esb18509\RPA\Fantasy

:: 執行 Python 腳本 (請確認您的 python 指令正確，或帶入完整 Python 路徑)
python run_fantasy.py

echo.
echo ==========================================
echo   執行完畢！您可以關閉此視窗。
echo ==========================================
pause