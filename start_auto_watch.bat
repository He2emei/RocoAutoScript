@echo off
cd /d "%~dp0"
python -m roco_auto run --interval 30
pause
