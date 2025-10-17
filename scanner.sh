#!/bin/bash

# Unix/Linux shell script to run EarningsEdgeDetection CLI Scanner
# Activates virtual environment and runs the scanner

echo "Activating virtual environment..."
source venv/bin/activate

echo "Running EarningsEdgeDetection CLI Scanner..."
python3 scanner.py "$@"

echo ""
echo "Scanner finished."
