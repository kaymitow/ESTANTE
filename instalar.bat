@echo off
rem Abre o instalador do Estante (janela com as opcoes). Use "instalar.bat -Simular" para ver sem instalar nada.
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0instalar.ps1" %*
