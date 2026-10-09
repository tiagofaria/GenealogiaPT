@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Nao foi possivel encontrar o Python neste computador.
  echo Instale Python 3.11 ou mais recente e volte a tentar.
  pause
  exit /b 1
)
where magick >nul 2>nul
if errorlevel 1 (
  echo Nao foi possivel encontrar o ImageMagick neste computador.
  echo Instale o ImageMagick com suporte TIFF e volte a tentar.
  pause
  exit /b 1
)
python app.py
if errorlevel 1 pause
