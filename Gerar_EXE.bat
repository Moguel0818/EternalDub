@echo off
setlocal
chcp 65001 >nul
title Gerar o EternalDub.exe
cd /d "%~dp0"

rem  Uso:  Gerar_EXE.bat            -> pasta dist\EternalDub com o EternalDub.exe (recomendado)
rem         Gerar_EXE.bat arquivo    -> um unico dist\EternalDub.exe
rem  Usage: Gerar_EXE.bat            -> folder dist\EternalDub with EternalDub.exe (recommended)
rem         Gerar_EXE.bat arquivo    -> a single dist\EternalDub.exe

if /i "%~1"=="arquivo" set "ETERNALDUB_UM_ARQUIVO=1"

for %%F in (EternalDub_gui.py EternalDub_core.py EternalDub_emendas.py EternalDub_audio.py EternalDub_i18n.py detectar_atraso.py EternalDub.spec icone.png EternalDub.ico idiomas\en.json) do if not exist "%%F" (
  echo.
  echo  Falta o arquivo / Missing file: %%F
  echo  Coloque todos os arquivos do EternalDub na mesma pasta.
  echo  Put all EternalDub files in the same folder.
  echo.
  pause
  exit /b 1
)

set "PY="
python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
  py -3 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  echo.
  echo  Python 3 nao encontrado. Instale em python.org marcando "Add python.exe to PATH".
  echo  Python 3 not found. Install it from python.org with "Add python.exe to PATH" checked.
  echo.
  pause
  exit /b 1
)

echo.
echo  Instalando os componentes (so demora na primeira vez)...
echo  Installing the components (slow only the first time)...
%PY% -m pip install --upgrade pyinstaller numpy PySide6
if errorlevel 1 goto :erro

echo.
echo  Gerando o programa (pode levar alguns minutos)...
echo  Building the program (this can take a few minutes)...
%PY% -m PyInstaller EternalDub.spec --noconfirm --clean
if errorlevel 1 goto :erro

echo.
echo  Pronto! / Done!
if defined ETERNALDUB_UM_ARQUIVO (
  echo  dist\EternalDub.exe
  explorer dist
) else (
  echo  dist\EternalDub\EternalDub.exe
  explorer dist\EternalDub
)
echo.
echo  O FFmpeg nao vai junto: coloque ffmpeg.exe e ffprobe.exe ao lado do EternalDub.exe,
echo  ou rode no Prompt de Comando:  winget install Gyan.FFmpeg
echo  FFmpeg is not included: put ffmpeg.exe and ffprobe.exe next to EternalDub.exe,
echo  or run in a Command Prompt:  winget install Gyan.FFmpeg
echo.
pause
exit /b 0

:erro
echo.
echo  Deu erro. Copie o texto acima e relate em github.com/Moguel0818/EternalDub/issues
echo  Something went wrong. Copy the text above and report it at github.com/Moguel0818/EternalDub/issues
echo.
pause
exit /b 1
