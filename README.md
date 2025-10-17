# EarningsEdgeDetection CLI Scanner

A command-line tool for scanning earnings-based options opportunities. Automatically determines dates based on current time and outputs recommended tickers.

## Installation

### 1. Install Python

Download and install Python from the official website:
- **Windows**: https://www.python.org/downloads/windows/
- **macOS**: https://www.python.org/downloads/macos/
- **Linux**: Use your distribution's package manager (e.g., `sudo apt install python3` on Ubuntu)

### 2. Setup Virtual Environment

#### Windows (Command Prompt)
```cmd
win_setup.bat
```

#### Windows (PowerShell)
```powershell
.\win_setup.bat
```

#### Unix/Linux/macOS
```bash
./unix_setup.sh
```

### 3. Alternative Manual Setup

If the setup scripts don't work, you can manually set up the environment:

#### Windows
```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

#### Unix/Linux/macOS
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Run Scanner

#### Windows
```cmd
scanner.bat
```

#### Unix/Linux/macOS
```bash
./scanner.sh
```

### Command Line Options

- `python scanner.py` - Run scanner with current date
- `python scanner.py MM/DD/YYYY` - Run scanner with specified date
- `python scanner.py -l` - Run with list format
- `python scanner.py -i` - Run with iron fly calculations
- `python scanner.py -a TICKER` - Analyze a specific ticker
- `python scanner.py -a TICKER -i` - Analyze ticker with iron fly strategy
- `python scanner.py --parallel N` - Enable parallel processing with N workers
- `python scanner.py --forever N` - Repeat scan every N hours

### Examples

```bash
# Scan current date
python scanner.py

# Scan specific date
python scanner.py 03/20/2025

# List format only
python scanner.py -l

# Include iron fly calculations
python scanner.py -i

# Analyze specific ticker
python scanner.py -a AAPL

# Parallel processing with 4 workers
python scanner.py --parallel 4
```

## Features

- Automatically scans for earnings-based options opportunities
- Supports both pre-market and post-market earnings
- Tiered recommendations (Tier 1 and Tier 2)
- Iron fly strategy calculations
- Parallel processing support
- Export results to CSV and JSON formats

## Requirements

- Python 3.8+
- Virtual environment (recommended)
- Internet connection for data fetching
