"""
Logging utilities for the scanner.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

def setup_logging(log_dir: str = "logs") -> None:
    """
    Configure logging to both file and console with rotation.
    
    Args:
        log_dir: Directory to store log files
    """
    # Create logs directory if it doesn't exist
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_formatter = logging.Formatter(
        '%(message)s'  # Simpler format for console
    )
    
    # File handler with current date
    file_handler = logging.FileHandler(
        f"{log_dir}/scanner_{datetime.now().strftime('%Y%m%d')}.log"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler - only show warnings and errors to avoid cluttering rich output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.WARNING)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # Clear any existing handlers
    root_logger.handlers.clear()
    # Add our handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Suppress some noisy loggers
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('yfinance').setLevel(logging.WARNING)