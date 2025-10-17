# EarningsEdgeDetection CLI Scanner

A command-line tool for scanning earnings-based options opportunities. Automatically determines dates based on current time and outputs recommended tickers.

## Getting the Code

### Option 1: Clone from GitHub (Recommended)
```bash
git clone https://github.com/YifanWang2002/EarningsScanner.git
cd EarningsScanner
```

### Option 2: Download ZIP from GitHub UI
1. Visit: https://github.com/YifanWang2002/EarningsScanner
2. Click the green "Code" button
3. Select "Download ZIP"
4. Extract the downloaded ZIP file to your desired location
5. Navigate to the extracted folder in your terminal/command prompt

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

## Configuration

The scanner uses a `config.json` file to store all filtering thresholds and operational settings. You can customize the behavior by modifying this file.

### Key Configuration Sections

#### Stock Filters
- **Price thresholds**: Minimum stock price and near-miss ranges
- **Volume requirements**: Minimum trading volume thresholds
- **Open interest**: Minimum options open interest required
- **Expected move**: Minimum expected earnings move in dollars
- **ATM delta limits**: Maximum delta for at-the-money options

#### IV/RV Filters
- **Pass/Near-miss thresholds**: Implied volatility to realized volatility ratios
- **Market adjustments**: Dynamic threshold relaxation based on market conditions

#### Term Structure Filters
- **Pass threshold**: Maximum negative term structure slope allowed
- **Near-miss threshold**: More lenient term structure requirement for Tier 2

#### Win Rate Filters
- **Pass threshold**: Minimum historical win rate for passing stocks
- **Near-miss threshold**: Lower threshold for near-miss categorization

#### Processing Settings
- **Batch size**: Number of stocks to process in each batch
- **Max workers**: Maximum parallel processing threads
- **Timeouts**: Various timeout values for network operations
- **Retries**: Maximum retry attempts for browser operations

### Example Configuration Changes

To make the scanner more strict (require higher quality stocks):
```json
{
  "stock_filters": {
    "price": {
      "minimum": 15.0,
      "near_miss_minimum": 10.0
    },
    "volume": {
      "minimum": 2000000
    }
  },
  "iv_rv_filters": {
    "pass_threshold": 1.4,
    "near_miss_threshold": 1.1
  }
}
```

To make the scanner more lenient (include more stocks):
```json
{
  "stock_filters": {
    "price": {
      "minimum": 5.0,
      "near_miss_minimum": 3.0
    },
    "expected_move": {
      "minimum_dollars": 0.5
    }
  }
}
```

### Using Custom Config File

You can specify a custom configuration file when running the scanner:
```bash
python scanner.py --config my_config.json
```

## Features

- Automatically scans for earnings-based options opportunities
- Supports both pre-market and post-market earnings
- Tiered recommendations (Tier 1 and Tier 2)
- Iron fly strategy calculations
- Parallel processing support
- Export results to CSV and JSON formats
- Fully configurable via JSON config file

## Requirements

- Python 3.8+
- Virtual environment (recommended)
- Internet connection for data fetching
