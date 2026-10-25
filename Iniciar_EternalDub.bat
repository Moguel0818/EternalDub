@echo off
setlocal
chcp 65001 >nul
title EternalDub
cd /d "%~dp0"

for %%F in (EternalDub_gui.py EternalDub_core.py EternalDub_i18n.py detectar_atraso.py) do if not exist "%%F" (
  echo.
  echo  Falta o arquivo / Missing file: %%F
  echo  %~dp0
  echo  Coloque todos os arquivos do EternalDub na mesma pasta.
  echo  Put all EternalDub files in the same folder.
  echo.
  pause
  exit /b 1
)

call :procurar
if defined PY goto :run

echo.
echo  Instalando componentes (numpy, PySide6) - so na primeira vez...
echo  Installing components (numpy, PySide6) - first run only...
echo.
python -m pip install --upgrade numpy PySide6
if errorlevel 1 py -3 -m pip install --upgrade numpy PySide6
call :procurar
if defined PY goto :run

echo.
echo  Nao consegui instalar. Confira se o Python 3 esta instalado (python.org,
echo  marcando "Add python.exe to PATH") e rode este arquivo de novo.
echo  Could not install. Make sure Python 3 is installed (python.org, with
echo  "Add python.exe to PATH" checked) and run this file again.
echo.
pause
exit /b 1

:run
echo.
echo  Abrindo o EternalDub... / Starting EternalDub...
echo  (nao feche esta janela / do not close this window)
%PY% EternalDub_gui.py
if errorlevel 1 pause
exit /b

:procurar
set "PY="
python -c "import numpy, PySide6" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY exit /b 0
py -3 -c "import numpy, PySide6" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
exit /b 0
