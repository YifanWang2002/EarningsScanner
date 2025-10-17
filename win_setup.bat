@echo off
REM Windows setup script for EarningsEdgeDetection CLI Scanner
REM This script creates a virtual environment, activates it, and installs requirements

echo Creating virtual environment...
python -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing requirements...
pip install -r requirements.txt

echo Setup complete! Virtual environment is activated.
echo You can now run the scanner using: python scanner.py
echo To deactivate the environment later, use: deactivate
