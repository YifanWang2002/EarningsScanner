#!/bin/bash

# Unix/Linux setup script for EarningsEdgeDetection CLI Scanner
# This script creates a virtual environment, activates it, and installs requirements

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing requirements..."
pip install -r requirements.txt

echo "Setup complete! Virtual environment is activated."
echo "You can now run the scanner using: python3 scanner.py"
echo "To deactivate the environment later, use: deactivate"
