@echo off
setlocal EnableExtensions
title Safe-Send - local setup and run
cd /d "%~dp0"

if "%INVESTIGATOR_API_KEY%"=="" set INVESTIGATOR_API_KEY=api-key-321
set PORT=8000

echo.
echo ===== Safe-Send =====

rem ---------- 1. Python ----------
python -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [1/6] Python not found. Installing with winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python was installed. Close this window and run run.bat again.
  pause
  exit /b 0
) else (
  echo [1/6] Python found - skipping install.
)

rem ---------- 2. Node.js ----------
where npm >nul 2>&1
if errorlevel 1 (
  echo [2/6] Node.js not found. Installing with winget...
  winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
  echo.
  echo Node.js was installed. Close this window and run run.bat again.
  pause
  exit /b 0
) else (
  echo [2/6] Node.js found - skipping install.
)

rem ---------- 3. Python packages ----------
python -c "import fastapi, uvicorn, lightgbm, shap, pandas, sklearn, networkx" >nul 2>&1
if errorlevel 1 (
  echo [3/6] Installing Python packages...
  python -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
) else (
  echo [3/6] Python packages already installed - skipping.
)

rem ---------- 4. Data and model ----------
if not exist "models\risk_model.pkl" (
  echo [4/6] Generating data and training the model - this takes a few minutes...
  python -m src.data_gen.generate --out data --seed 42
  if errorlevel 1 goto :fail
  python -m src.features.build --data data --out data/features.csv
  if errorlevel 1 goto :fail
  python -m src.models.train --data data
  if errorlevel 1 goto :fail
) else (
  echo [4/6] Model already trained - skipping.
)

rem ---------- 5. Frontend ----------
if not exist "frontend\node_modules" (
  echo [5/6] Installing frontend packages...
  pushd frontend
  call npm install
  if errorlevel 1 ( popd & goto :fail )
  popd
) else (
  echo [5/6] Frontend packages already installed - skipping.
)
if not exist "frontend\dist\index.html" (
  echo       Building frontend...
  pushd frontend
  call npm run build
  if errorlevel 1 ( popd & goto :fail )
  popd
) else (
  echo       Frontend already built - skipping. Delete frontend\dist to rebuild.
)

rem ---------- 6. Run ----------
echo [6/6] Starting the app...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  echo       Port %PORT% is busy - stopping the old process %%p
  taskkill /PID %%p /F >nul 2>&1
)
echo.
echo   App:           http://localhost:%PORT%
echo   Investigator:  http://localhost:%PORT%/investigator   (key: %INVESTIGATOR_API_KEY%)
echo   Press Ctrl+C to stop.
echo.
start "" /min cmd /c "timeout /t 20 >nul & start http://localhost:%PORT%"
python -m uvicorn src.api.main:app --port %PORT%
goto :end

:fail
echo.
echo Something went wrong. Read the messages above.
:end
pause
