@echo off
rem Launcher for PowerShell / cmd: runs the engagent CLI from the project environment.
if exist "%~dp0.venv\Scripts\engagent.exe" (
  "%~dp0.venv\Scripts\engagent.exe" %*
) else (
  echo EngineeringAgent is not installed here. Run: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  exit /b 127
)
