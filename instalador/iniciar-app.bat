@echo off
rem Abre o Estante, sem janela de terminal. Este arquivo fica na pasta instalador; o app e a pasta de cima.
cd /d "%~dp0.."
if not exist .venv\Scripts\pythonw.exe (
  echo O Estante ainda nao foi instalado nesta pasta. Rode instalar.bat primeiro.
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw.exe app\abrir.py
