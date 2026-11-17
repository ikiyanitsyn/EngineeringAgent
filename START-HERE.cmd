@echo off
rem Double-click me. First run installs everything (no admin rights needed), then shows a menu.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
