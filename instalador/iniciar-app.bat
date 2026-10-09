@echo off
rem Abre o Estante. Este arquivo fica na pasta instalador; o app é a pasta de cima.
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo O Estante ainda nao foi instalado nesta pasta. Rode instalar.bat primeiro.
  pause
  exit /b 1
)
rem abre a tela uns segundos depois, quando o servidor ja esta respondendo
rem com o Edge instalado, abre em janela propria (sem abas nem barra de endereco); sem ele, no navegador padrao
set "ABRE=start http://127.0.0.1:8765"
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" >nul 2>&1 && set "ABRE=start msedge --app=http://127.0.0.1:8765"
start "" /min cmd /c "timeout /t 3 /nobreak >nul & %ABRE%"
.venv\Scripts\python.exe app\servidor.py
