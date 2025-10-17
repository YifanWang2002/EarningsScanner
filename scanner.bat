@echo off
REM Windows batch script to run EarningsEdgeDetection CLI Scanner
REM Activates virtual environment and runs the scanner

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Running EarningsEdgeDetection CLI Scanner...
python scanner.py %*

echo.
echo Scanner finished. Press any key to exit.
pause >nul
