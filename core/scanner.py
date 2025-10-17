"""
Earnings scanner that handles date logic and filtering.
"""

import logging
import re
import time
import csv
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytz
import requests
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import yfinance as yf
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from .analyzer import OptionsAnalyzer
import core.yfinance_cookie_patch

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

core.yfinance_cookie_patch.patch_yfdata_cookie_basic()
session = curl_requests.Session(impersonate="chrome")
console = Console()

class EarningsScanner:
    # Initialize class variables, only one __init__ method should exist
    def __del__(self):
        # Clean up browser when scanner is destroyed
        if hasattr(self, '_driver') and self._driver is not None:
            try:
                self._driver.quit()
            except Exception as e:
                # Just silently ignore errors during cleanup
                pass
                
    def calculate_iron_fly_strikes(self, ticker: str) -> Dict[str, any]:
        """
        Calculate recommended iron fly strikes based on options closest to 50 delta.
        
        Returns a dictionary containing:
        - short_call_strike: Strike price of the short call (near 50 delta)
        - short_put_strike: Strike price of the short put (near 50 delta)
        - long_call_strike: Strike price of the long call (wing)
        - long_put_strike: Strike price of the long put (wing)
        - short_call_premium: Premium received for short call
        - short_put_premium: Premium received for short put
        - total_credit: Total credit received for the short strikes
        - wing_width: The width used for the wings (3x credit)
        """
        try:
            # Get ticker data
            ticker_obj = yf.Ticker(ticker, session=session)
            if not ticker_obj.options or len(ticker_obj.options) == 0:
                return {"error": "No options available"}
            
            # Get the nearest expiration
            expiry = ticker_obj.options[0]
            
            # Get the options chain
            opt_chain = ticker_obj.option_chain(expiry)
            calls = opt_chain.calls
            puts = opt_chain.puts
            
            # Current price
            current_price = ticker_obj.history(period='1d')['Close'].iloc[-1]
            
            # Check if delta column exists
            if 'delta' in calls.columns and 'delta' in puts.columns:
                # Find call closest to 50 delta (absolute value)
                calls['delta_diff'] = abs(abs(calls['delta']) - 0.5)
                closest_call = calls.loc[calls['delta_diff'].idxmin()]
                short_call_strike = closest_call['strike']
                short_call_premium = (closest_call['bid'] + closest_call['ask']) / 2
                
                # Find put closest to 50 delta (absolute value)
                puts['delta_diff'] = abs(abs(puts['delta']) - 0.5)
                closest_put = puts.loc[puts['delta_diff'].idxmin()]
                short_put_strike = closest_put['strike']
                short_put_premium = (closest_put['bid'] + closest_put['ask']) / 2
            else:
                # If delta not available, use strike closest to current price
                # Find call closest to ATM
                calls['price_diff'] = abs(calls['strike'] - current_price)
                closest_call = calls.loc[calls['price_diff'].idxmin()]
                short_call_strike = closest_call['strike']
                short_call_premium = (closest_call['bid'] + closest_call['ask']) / 2
                
                # Find put closest to ATM
                puts['price_diff'] = abs(puts['strike'] - current_price)
                closest_put = puts.loc[puts['price_diff'].idxmin()]
                short_put_strike = closest_put['strike']
                short_put_premium = (closest_put['bid'] + closest_put['ask']) / 2
            
            # Calculate total credit
            total_credit = short_call_premium + short_put_premium
            
            # Calculate wing width - 3x the credit received
            wing_width = 3 * total_credit
            
            # Calculate wing strikes
            long_put_strike = short_put_strike - wing_width
            long_call_strike = short_call_strike + wing_width
            
            # Find actual option strikes that are closest to calculated wings
            available_put_strikes = sorted(puts['strike'].unique())
            available_call_strikes = sorted(calls['strike'].unique())
            
            # Find closest available strikes for wings
            long_put_strike = min(available_put_strikes, key=lambda x: abs(x - long_put_strike))
            long_call_strike = min(available_call_strikes, key=lambda x: abs(x - long_call_strike))
            
            # Find prices for long positions
            long_put_option = puts[puts['strike'] == long_put_strike].iloc[0]
            long_call_option = calls[calls['strike'] == long_call_strike].iloc[0]
            long_put_premium = round((long_put_option['bid'] + long_put_option['ask']) / 2, 2)
            long_call_premium = round((long_call_option['bid'] + long_call_option['ask']) / 2, 2)
            
            # Calculate actual wing widths
            put_wing_width = short_put_strike - long_put_strike
            call_wing_width = long_call_strike - short_call_strike
            
            # Calculate max profit and max risk
            total_debit = long_put_premium + long_call_premium
            net_credit = total_credit - total_debit
            max_profit = net_credit
            max_risk = min(put_wing_width, call_wing_width) - net_credit
            
            # Calculate break-even points
            upper_breakeven = short_call_strike + net_credit
            lower_breakeven = short_put_strike - net_credit
            
            # Calculate risk-reward ratio
            risk_reward_ratio = round(max_risk / max_profit, 1) if max_profit > 0 else float('inf')
            
            # Round values for display
            short_call_strike = round(short_call_strike, 2)
            short_put_strike = round(short_put_strike, 2)
            long_call_strike = round(long_call_strike, 2)
            long_put_strike = round(long_put_strike, 2)
            short_call_premium = round(short_call_premium, 2)
            short_put_premium = round(short_put_premium, 2)
            total_credit = round(total_credit, 2)
            put_wing_width = round(put_wing_width, 2)
            call_wing_width = round(call_wing_width, 2)
            max_profit = round(max_profit, 2)
            max_risk = round(max_risk, 2)
            
            return {
                "short_call_strike": short_call_strike,
                "short_put_strike": short_put_strike,
                "long_call_strike": long_call_strike,
                "long_put_strike": long_put_strike,
                "short_call_premium": short_call_premium,
                "short_put_premium": short_put_premium,
                "long_call_premium": long_call_premium,
                "long_put_premium": long_put_premium,
                "total_credit": round(total_credit, 2),
                "total_debit": round(total_debit, 2),
                "net_credit": round(net_credit, 2),
                "put_wing_width": put_wing_width,
                "call_wing_width": call_wing_width,
                "max_profit": max_profit,
                "max_risk": max_risk,
                "upper_breakeven": round(upper_breakeven, 2),
                "lower_breakeven": round(lower_breakeven, 2),
                "risk_reward_ratio": risk_reward_ratio,
                "expiration": expiry
            }
        except Exception as e:
            logger.warning(f"Error calculating iron fly for {ticker}: {e}")
            return {"error": str(e)}
    
    from datetime import datetime, timedelta, date
    from typing import Optional, Tuple
    import logging

    logger = logging.getLogger(__name__)

    def get_scan_dates(self, input_date: Optional[str] = None) -> Tuple[date, date]:
        if input_date:
            try:
                post_date = datetime.strptime(input_date, '%m/%d/%Y').date()
                logger.info(f"Using provided date: post-market {post_date}")
            except ValueError as e:
                logger.error(f"Invalid date format: {e}")
                raise ValueError("Please provide date in MM/DD/YYYY format")
        else:
            now = datetime.now(self.eastern_tz)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            post_date = now.date() if now < market_close else (now + timedelta(days=1)).date()

        # Determine pre_date
        if post_date.weekday() == 4:  # Friday (0=Mon, 4=Fri)
            pre_date = post_date + timedelta(days=3)  # Next Monday
        elif post_date.weekday() == 5:  # Saturday
            pre_date = post_date + timedelta(days=2)  # Next Monday
        else:
            pre_date = post_date + timedelta(days=1)

        logger.info(f"Computed scan dates: post-market {post_date}, pre-market {pre_date}")
        return post_date, pre_date


            
    
    
    # Initialize class variables, only one __init__ method should exist
    def __init__(self, eastern_tz=pytz.timezone('US/Eastern')):  # Constructor with eastern timezone parameter
        # Default parameter values initialization
        self.eastern_tz = eastern_tz
        self.batch_size = 8  # Default batch size
        # Default threshold values for IV/RV ratio
        self.iv_rv_pass_threshold = 1.25
        self.iv_rv_near_miss_threshold = 1.0
        # Initialize the analyzer
        self.analyzer = OptionsAnalyzer()
    
    
    def fetch_earnings_data(self, date: datetime.date) -> List[Dict]:
        """
        Get earnings data from Investing.com.
        """
        return self._get_investing_earnings_data(date)
    
    def _get_investing_earnings_data(self, date: datetime.date) -> List[Dict]:
        """Get earnings data from Investing.com"""
        url = "https://www.investing.com/earnings-calendar/Service/getCalendarFilteredData"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://www.investing.com/earnings-calendar/'
        }
        
        payload = {
            'country[]': '5',
            'dateFrom': date.strftime('%Y-%m-%d'),
            'dateTo': date.strftime('%Y-%m-%d'),
            'currentTab': 'custom',
            'limit_from': 0
        }
        
        try:
            # Add a user-agent rotation to avoid blocking
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
                'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            ]
            import random
            headers['User-Agent'] = random.choice(user_agents)
            
            response = requests.post(url, headers=headers, data=payload, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            # Try to parse JSON response
            data = response.json()
            
            # Check if data has the expected structure
            if 'data' not in data:
                logger.warning("Invalid response format from Investing.com API")
                return []
                
            soup = BeautifulSoup(data['data'], 'html.parser')
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Error fetching earnings data: {e}")
            return []
        
        rows = soup.find_all('tr')
        
        stocks = []
        for row in rows:
            if not row.find('span', class_='earnCalCompanyName'):
                continue
            
            try:
                ticker = row.find('a', class_='bold').text.strip()
                timing_span = row.find('span', class_='genToolTip')
                
                if timing_span and 'data-tooltip' in timing_span.attrs:
                    tooltip = timing_span['data-tooltip']
                    if tooltip == 'Before market open':
                        timing = 'Pre Market'
                    elif tooltip == 'After market close':
                        timing = 'Post Market'
                    else:
                        timing = 'During Market'
                else:
                    timing = 'Unknown'
                
                stocks.append({'ticker': ticker, 'timing': timing})
                
            except Exception as e:
                logger.warning(f"Error parsing row: {e}")
                continue
        
        return stocks

    _driver = None  # Reusable browser instance
    _driver_lock = None  # Thread lock for browser access
    _max_retries = 3  # Number of retry attempts for browser operations
    
    def _initialize_browser(self):
        """Initialize or reinitialize the browser with optimized settings"""
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Close any existing instance first
        if self._driver is not None:
            try:
                self._driver.quit()
            except:
                pass
            self._driver = None
        
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        options.add_argument('--blink-settings=imagesEnabled=false')
        options.add_argument('--js-flags=--expose-gc')
        options.add_argument('--disable-dev-shm-usage')
        
        # Additional memory optimization
        options.add_argument('--disable-browser-side-navigation')
        options.add_argument('--disable-3d-apis')
        options.add_argument('--disable-accelerated-2d-canvas')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=NetworkPrediction,PrefetchDNSOverride')
        options.add_argument('--disable-sync')
        options.add_argument('--mute-audio')
        options.add_argument('--no-first-run')
        options.add_argument('--no-default-browser-check')
        options.add_argument('--memory-model=low')
        options.add_argument('--disable-translate')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        
        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)
        self._driver.set_page_load_timeout(10)  # Even shorter timeout
        
    def check_mc_overestimate(self, ticker: str) -> Dict[str, any]:
        """Get Market Chameleon overestimate data with retry mechanism"""
        import threading
        
        # Initialize thread lock if needed
        if self._driver_lock is None:
            self._driver_lock = threading.Lock()
        
        # Default return values
        default_result = {'win_rate': 0.0, 'quarters': 0}
        
        # Acquire lock for thread safety
        with self._driver_lock:
            # Try to initialize browser if not already running
            if self._driver is None:
                try:
                    self._initialize_browser()
                except Exception as e:
                    logger.error(f"Failed to initialize browser: {e}")
                    return default_result
            
            # Retry loop
            retries = 0
            while retries < self._max_retries:
                try:
                    # Check if browser needs reinitializing
                    try:
                        # Quick test if browser is responsive
                        self._driver.window_handles
                    except:
                        # Browser crashed or not responsive, reinitialize
                        logger.info(f"Browser needs reinitializing for {ticker}")
                        self._initialize_browser()
                    
                    url = f"https://marketchameleon.com/Overview/{ticker}/Earnings/Earnings-Charts/"
                    self._driver.get(url)
                    
                    wait = WebDriverWait(self._driver, 8)  # Even shorter timeout
                    section = wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, "symbol-section-header-descr"))
                    )
            
                    # Default results
                    win_rate = 0.0
                    quarters = 0
                    
                    # Extract both the percentage and quarters data
                    spans = section.find_elements(By.TAG_NAME, "span")
                    for span in spans:
                        if "overestimated" in span.text:
                            # Extract the percentage
                            try:
                                strong = span.find_element(By.TAG_NAME, "strong")
                                win_rate = float(strong.text.strip('%'))
                                
                                # Extract the quarters by parsing the text after the percentage
                                text = span.text
                                quarters_pattern = r"in the last (\d+) quarters"
                                quarters_match = re.search(quarters_pattern, text)
                                if quarters_match:
                                    quarters = int(quarters_match.group(1))
                            except Exception as inner_e:
                                logger.debug(f"Error extracting data for {ticker}: {inner_e}")
                            break
                    
                    # Success - return the data and break the retry loop
                    return {
                        'win_rate': win_rate,
                        'quarters': quarters
                    }
                    
                except Exception as e:
                    logger.warning(f"Error getting MC data for {ticker} (attempt {retries+1}/{self._max_retries}): {e}")
                    retries += 1
                    
                    # Try to reinitialize browser after each failure
                    try:
                        self._initialize_browser()
                    except:
                        pass
                    
                    # Small delay before retry
                    time.sleep(1)
            
            # If we get here, we've exhausted retries
            logger.error(f"Failed to get MC data for {ticker} after {self._max_retries} attempts")
            return default_result

    def validate_stock(self, stock: Dict) -> Dict:
        ticker = stock['ticker']
        analysis = None
        failed_checks = []
        near_miss_checks = []
        metrics = {'ticker': ticker}
        
        try:
            logger.debug(f"Validating {ticker}: Starting analysis...")
            yf_ticker = yf.Ticker(ticker, session=session)
            
            # Price check (first and fastest)
            logger.debug(f"Validating {ticker}: Checking price...")
            try:
                hist = yf_ticker.history(period='1d')
                if hist.empty:
                    logger.warning(f"{ticker}: No price history available")
                    return {
                        'pass': False,
                        'near_miss': False,
                        'reason': "No price data available",
                        'metrics': metrics
                    }
                current_price = hist['Close'].iloc[-1]
            except Exception as e:
                logger.warning(f"{ticker}: Error fetching price - {e}")
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Price fetch error: {str(e)}",
                    'metrics': metrics
                }
                
            metrics['price'] = current_price
            if current_price < 10.0:
                logger.debug(f"{ticker}: Failed price check - ${current_price:.2f} < $10.00")
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Price ${current_price:.2f} < $10.00",
                    'metrics': metrics
                }

            # Options availability and expiration check
            logger.debug(f"Validating {ticker}: Checking options availability...")
            options_dates = yf_ticker.options
            if not options_dates:
                logger.debug(f"{ticker}: No options available")
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': "No options available",
                    'metrics': metrics
                }

            # Check expiration date
            logger.debug(f"Validating {ticker}: Checking expiration date...")
            first_expiry = datetime.strptime(options_dates[0], "%Y-%m-%d").date()
            days_to_expiry = (first_expiry - datetime.now().date()).days
            metrics['days_to_expiry'] = days_to_expiry
            
            if days_to_expiry > 9:
                logger.debug(f"{ticker}: Expiration too far - {days_to_expiry} days")
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Next expiration too far: {days_to_expiry} days",
                    'metrics': metrics
                }

            # Check open interest
            logger.debug(f"Validating {ticker}: Checking open interest...")
            chain = yf_ticker.option_chain(options_dates[0])
            total_oi = chain.calls['openInterest'].sum() + chain.puts['openInterest'].sum()
            metrics['open_interest'] = total_oi
            
            if total_oi < 2000:
                logger.debug(f"{ticker}: Insufficient open interest - {total_oi}")
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Insufficient open interest: {total_oi}",
                    'metrics': metrics
                }
            
            # Mandatory check: core analysis
            logger.debug(f"Validating {ticker}: Running core analysis...")
            analysis = self.analyzer.compute_recommendation(ticker)
                
            if "error" in analysis:
                logger.warning(f"{ticker}: Core analysis failed - {analysis['error']}")
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Analysis error - {analysis['error']}",
                    'metrics': metrics
                }
            
            # Term structure check (immediate exit - this is a hard filter)
            logger.debug(f"Validating {ticker}: Checking term structure...")
            term_slope = analysis.get('term_slope', 0)
            metrics['term_structure'] = term_slope
            if term_slope > -0.004:
                logger.debug(f"{ticker}: Failed term structure - {term_slope:.4f} > -0.004")
                return {
                    'pass': False,
                    'near_miss': False,
                    'reason': f"Term structure {term_slope:.4f} > -0.004",
                    'metrics': metrics
                }
                
            # Check ATM option deltas to ensure they are not too far from 0.5
            # Only perform this check if delta values are available
            call_delta = analysis.get('atm_call_delta')
            put_delta = analysis.get('atm_put_delta')
            
            # Skip this check if either delta is None (not available from Yahoo Finance API)
            if call_delta is not None and put_delta is not None:
                try:
                    # Call delta should be <= 0.57 (not too deep ITM)
                    # Put delta should be >= -0.57 (absolute value <= 0.57)
                    call_delta_float = float(call_delta)
                    put_delta_float = float(put_delta)
                    
                    metrics['atm_call_delta'] = call_delta_float
                    metrics['atm_put_delta'] = put_delta_float
                    
                    if call_delta_float > 0.57 or abs(put_delta_float) > 0.57:
                        return {
                            'pass': False,
                            'near_miss': False,
                            'reason': f"ATM options have delta > 0.57 (call: {call_delta_float:.2f}, put: {put_delta_float:.2f})",
                            'metrics': metrics
                        }
                except (TypeError, ValueError) as e:
                    # Log more details about the error
                    logger.debug(f"Skipping delta check for {ticker}: invalid delta values - {e}. Values: call_delta={call_delta}, put_delta={put_delta}")
            
            # Check for minimum expected move of $0.90
            expected_move_pct = analysis.get('expected_move', 'N/A')
            
            # Log the raw expected move value for debugging
            logger.debug(f"Raw expected move for {ticker}: {expected_move_pct}")
            
            if expected_move_pct != 'N/A':
                # Parse the percentage from the string (e.g., "5.20%")
                try:
                    # Handle both string and numeric formats
                    if isinstance(expected_move_pct, str):
                        move_pct = float(expected_move_pct.strip('%')) / 100
                    else:
                        move_pct = float(expected_move_pct) / 100
                        
                    expected_move_dollars = current_price * move_pct
                    metrics['expected_move_dollars'] = expected_move_dollars
                    metrics['expected_move_pct'] = move_pct * 100
                    
                    logger.debug(f"Calculated expected move for {ticker}: ${expected_move_dollars:.2f} ({move_pct*100:.2f}%)")
                    
                    # Reject if expected move is less than $0.90
                    if expected_move_dollars < 0.9:
                        return {
                            'pass': False,
                            'near_miss': False,
                            'reason': f"Expected move ${expected_move_dollars:.2f} < $0.90",
                            'metrics': metrics
                        }
                except (ValueError, AttributeError, TypeError) as e:
                    logger.warning(f"Could not parse expected move for {ticker}: {expected_move_pct} - Error: {e}")
                    
                    # As a fallback, try to calculate expected move from ATM option premiums
                    try:
                        if 'options_dates' in locals() and len(options_dates) > 0:
                            chain = yf_ticker.option_chain(options_dates[0])
                            calls, puts = chain.calls, chain.puts
                            
                            call_idx = (calls['strike'] - current_price).abs().idxmin()
                            put_idx = (puts['strike'] - current_price).abs().idxmin()
                            
                            call_mid = (calls.loc[call_idx, 'bid'] + calls.loc[call_idx, 'ask']) / 2
                            put_mid = (puts.loc[put_idx, 'bid'] + puts.loc[put_idx, 'ask']) / 2
                            straddle = call_mid + put_mid
                            
                            # Using the straddle price as a direct estimate of expected move in dollars
                            expected_move_dollars = straddle
                            metrics['expected_move_dollars'] = expected_move_dollars
                            metrics['expected_move_pct'] = (expected_move_dollars / current_price) * 100
                            
                            logger.info(f"Using fallback method for expected move on {ticker}: ${expected_move_dollars:.2f} ({metrics['expected_move_pct']:.2f}%)")
                            
                            if expected_move_dollars < 0.9:
                                return {
                                    'pass': False,
                                    'near_miss': False,
                                    'reason': f"Expected move (fallback) ${expected_move_dollars:.2f} < $0.90",
                                    'metrics': metrics
                                }
                    except Exception as e2:
                        logger.warning(f"Fallback expected move calculation also failed for {ticker}: {e2}")
            
            # Non-mandatory checks with near-miss ranges
            # Price check
            current_price = yf_ticker.history(period='1d')['Close'].iloc[-1]
            metrics['price'] = current_price
            if current_price < 5.0:
                failed_checks.append(f"Price ${current_price:.2f} < $5.00")
            elif current_price < 7.0:
                near_miss_checks.append(f"Price ${current_price:.2f} < $7.00")
                
            # Volume check
            avg_volume = yf_ticker.history(period='1mo')['Volume'].mean()
                
            metrics['volume'] = avg_volume
            if avg_volume < 1_000_000:
                failed_checks.append(f"Volume {avg_volume:,.0f} < 1M")
            elif avg_volume < 1_500_000:
                near_miss_checks.append(f"Volume {avg_volume:,.0f} < 1.5M") 

            # Market Chameleon check - only if we haven't failed already
            if not failed_checks:  # Skip if already failing other checks
                mc_data = self.check_mc_overestimate(ticker)
                win_rate = mc_data['win_rate']
                quarters = mc_data['quarters']
                
                # Store both percentage and quarters in metrics
                metrics['win_rate'] = win_rate
                metrics['win_quarters'] = quarters
                
                # Apply the new threshold of 50%
                if win_rate < 50.0:
                    if win_rate >= 40.0:  # Between 40-50% is now a near miss
                        near_miss_checks.append(f"Winrate {win_rate}% < 50% (over {quarters} earnings)")
                    else:  # Below 40% is still a failure
                        failed_checks.append(f"Winrate {win_rate}% < 40% (over {quarters} earnings)")
            else:
                # Add placeholders if we skip
                metrics['win_rate'] = 0.0
                metrics['win_quarters'] = 0
            
            # IV/RV check
            iv_rv_ratio = analysis.get('iv30_rv30', 0)
            metrics['iv_rv_ratio'] = iv_rv_ratio

            # Use dynamic thresholds based on market conditions
            if iv_rv_ratio < self.iv_rv_near_miss_threshold:
                failed_checks.append(f"IV/RV ratio {iv_rv_ratio:.2f} < {self.iv_rv_near_miss_threshold}")
            elif iv_rv_ratio < self.iv_rv_pass_threshold:
                near_miss_checks.append(f"IV/RV ratio {iv_rv_ratio:.2f} < {self.iv_rv_pass_threshold}")

            # Determine final categorization
            
            # Is this a passing stock (original criteria)?
            is_passing = len(failed_checks) == 0 and len(near_miss_checks) == 0
            
            # Is this a near miss with good term structure?
            is_near_miss_good_term = (len(failed_checks) == 0 and 
                                      len(near_miss_checks) > 0 and 
                                      term_slope <= -0.006)
            
            # Assign tiers:
            # - Tier 1: Original "recommended" stocks (passing all criteria)
            # - Tier 2: Near misses with term structure <= -0.006
            # - Near misses: The rest (term structure must still be <= -0.004)
            if is_passing:
                tier = 1
                metrics['tier'] = 1
                is_tier2 = False
                is_near_miss = False
            elif is_near_miss_good_term:
                tier = 2
                metrics['tier'] = 2
                is_tier2 = True
                is_near_miss = False
            else:
                tier = 0
                metrics['tier'] = 0
                is_tier2 = False
                is_near_miss = len(failed_checks) == 0  # Only a near miss if it only fails non-critical checks

            return {
                'pass': is_passing or is_tier2,  # Both Tier 1 and Tier 2 pass
                'tier': tier,
                'near_miss': is_near_miss,
                'reason': " | ".join(failed_checks) if failed_checks else (
                    " | ".join(near_miss_checks) if near_miss_checks else 
                    "Tier 1 Trade" if is_passing else 
                    "Tier 2 Trade" if is_tier2 else 
                    "Near Miss"
                ),
                'metrics': metrics
            }

        except Exception as e:
            logger.warning(f"Error validating {ticker}: {e}")
            return {
                'pass': False,
                'near_miss': False,
                'metrics': {},
                'reason': f"Validation error: {str(e)}"
            }

    def adjust_thresholds_based_on_spy(self):
        """
        Check SPY's current IV/RV ratio and adjust thresholds if market IV is low.
        If SPY IV/RV <= 1.1, reduce thresholds by 0.1.
        """
        try:
            # Calculate SPY's IV/RV
            spy_analysis = self.analyzer.compute_recommendation('SPY')
            if 'error' not in spy_analysis:
                spy_iv_rv = spy_analysis.get('iv30_rv30', 0)
                
                # Check if the IV/RV ratio is unreasonably low (likely due to market being closed)
                if spy_iv_rv < 0.01:  # IV/RV below 0.01 is likely bad data
                    logger.warning(f"SPY IV/RV ratio ({spy_iv_rv:.4f}) is unreasonably low - likely due to closed market or data issue")
                    logger.info("Using standard thresholds due to unreliable SPY data")
                    logger.info(f"Current IV/RV thresholds - Pass: {self.iv_rv_pass_threshold}, Near Miss: {self.iv_rv_near_miss_threshold}")
                    return
                
                logger.info(f"Current SPY IV/RV ratio: {spy_iv_rv:.2f}")
                
                # Three-tiered threshold system based on market conditions
                if spy_iv_rv <= 0.75:  # Severe low volatility (new tier)
                    self.iv_rv_pass_threshold = 0.90  # Relaxed by 0.35
                    self.iv_rv_near_miss_threshold = 0.65  # Relaxed by 0.35
                    logger.info(f"Market IV/RV is severely low ({spy_iv_rv:.2f}). Relaxing IV/RV thresholds by 0.35")
                elif spy_iv_rv <= 0.85:  # Extreme low volatility
                    self.iv_rv_pass_threshold = 1.00  # Relaxed by 0.25
                    self.iv_rv_near_miss_threshold = 0.75  # Relaxed by 0.25
                    logger.info(f"Market IV/RV is extremely low ({spy_iv_rv:.2f}). Relaxing IV/RV thresholds by 0.25")
                elif spy_iv_rv <= 1.0:  # Moderately low volatility
                    self.iv_rv_pass_threshold = 1.10  # Relaxed by 0.15
                    self.iv_rv_near_miss_threshold = 0.85  # Relaxed by 0.15
                    logger.info(f"Market IV/RV is low ({spy_iv_rv:.2f}). Relaxing IV/RV thresholds by 0.15")
                else:  # Normal market conditions
                    logger.info(f"Normal market IV/RV ({spy_iv_rv:.2f}). Using standard thresholds")
                
                logger.info(f"Current IV/RV thresholds - Pass: {self.iv_rv_pass_threshold}, Near Miss: {self.iv_rv_near_miss_threshold}")
            else:
                logger.warning(f"Could not calculate SPY IV/RV: {spy_analysis.get('error')}")
                logger.info(f"Using standard IV/RV thresholds - Pass: {self.iv_rv_pass_threshold}, Near Miss: {self.iv_rv_near_miss_threshold}")
        except Exception as e:
            logger.warning(f"Error calculating SPY IV/RV: {e}")
            logger.info(f"Using standard IV/RV thresholds - Pass: {self.iv_rv_pass_threshold}, Near Miss: {self.iv_rv_near_miss_threshold}")
            
    def analyze_ticker(self, ticker: str) -> Dict:
        """
        Analyze a specific ticker symbol and return detailed results regardless of pass/fail status.
        
        Args:
            ticker: The ticker symbol to analyze (e.g., 'AAPL', 'MSFT')
            
        Returns:
            Dictionary containing all metrics and validation results
        """
        try:
            # Create a stock dict as expected by validate_stock
            stock = {'ticker': ticker, 'timing': 'Manual Check'}
            
            # Adjust thresholds based on market conditions
            self.adjust_thresholds_based_on_spy()
            
            # Run all validation checks on this stock
            result = self.validate_stock(stock)
            
            # Get all available metrics
            metrics = result.get('metrics', {}) if 'metrics' in result else {}
            
            # Add pass/fail status to the metrics
            metrics['pass'] = result.get('pass', False)
            metrics['near_miss'] = result.get('near_miss', False) 
            metrics['tier'] = result.get('tier', 0) if 'tier' in result else 0
            metrics['reason'] = result.get('reason', "Unknown status")
            
            # Add current thresholds used for context
            metrics['iv_rv_pass_threshold'] = self.iv_rv_pass_threshold
            metrics['iv_rv_near_miss_threshold'] = self.iv_rv_near_miss_threshold
            
            # Add SPY IV/RV info
            try:
                spy_analysis = self.analyzer.compute_recommendation('SPY')
                if 'error' not in spy_analysis:
                    metrics['spy_iv_rv'] = spy_analysis.get('iv30_rv30', 0)
            except:
                metrics['spy_iv_rv'] = 'N/A'
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error analyzing ticker {ticker}: {e}")
            return {
                'error': str(e),
                'pass': False,
                'near_miss': False,
                'reason': f"Analysis error: {str(e)}"
            }
            
    def export_to_csv(self, stock_metrics: Dict[str, Dict], recommended: List[str], 
                     near_misses: List[Tuple[str, str]], all_analyzed: Dict[str, Dict]) -> str:
        """Export all ticker data to CSV files.
        
        Creates two CSV files:
        1. all_tickers_analyzed.csv - All tickers that were analyzed with their metrics
        2. final_results.csv - Flattened final results with categorization
        
        Returns the directory path where files were saved.
        """
        # Create output directory with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = Path(f"scan_results_{timestamp}")
        output_dir.mkdir(exist_ok=True)
        
        # Export all analyzed tickers
        all_tickers_file = output_dir / "all_tickers_analyzed.csv"
        with open(all_tickers_file, 'w', newline='') as f:
            # Collect all possible field names from metrics
            all_fields = set()
            for metrics in all_analyzed.values():
                all_fields.update(metrics.keys())
            
            # Define preferred field order (including 'status' which we'll add)
            preferred_order = ['ticker', 'status', 'tier', 'price', 'volume', 'term_structure', 
                             'iv_rv_ratio', 'win_rate', 'win_quarters', 'expected_move_dollars',
                             'expected_move_pct', 'open_interest', 'days_to_expiry', 'reason']
            
            # Add 'status' to all_fields since we'll be adding it to each row
            all_fields.add('status')
            all_fields.add('ticker')
            
            # Arrange fields with preferred ones first
            fieldnames = [f for f in preferred_order if f in all_fields]
            fieldnames.extend([f for f in sorted(all_fields) if f not in fieldnames])
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for ticker, metrics in all_analyzed.items():
                row = {'ticker': ticker}
                row.update(metrics)
                # Add status
                if ticker in recommended:
                    row['status'] = 'RECOMMENDED'
                elif ticker in [t for t, _ in near_misses]:
                    row['status'] = 'NEAR_MISS'
                else:
                    row['status'] = 'FAILED'
                writer.writerow(row)
        
        # Export final results summary
        final_results_file = output_dir / "final_results.csv"
        with open(final_results_file, 'w', newline='') as f:
            fieldnames = ['ticker', 'category', 'tier', 'price', 'volume', 'term_structure',
                         'iv_rv_ratio', 'win_rate', 'win_quarters', 'expected_move_dollars', 'reason']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            # Write Tier 1 recommendations
            for ticker in recommended:
                if ticker in stock_metrics and stock_metrics[ticker].get('tier') == 1:
                    row = {
                        'ticker': ticker,
                        'category': 'TIER_1_RECOMMENDED',
                        'tier': 1,
                        **{k: stock_metrics[ticker].get(k, '') for k in fieldnames[3:]}
                    }
                    writer.writerow(row)
            
            # Write Tier 2 recommendations
            for ticker in recommended:
                if ticker in stock_metrics and stock_metrics[ticker].get('tier') == 2:
                    row = {
                        'ticker': ticker,
                        'category': 'TIER_2_RECOMMENDED',
                        'tier': 2,
                        **{k: stock_metrics[ticker].get(k, '') for k in fieldnames[3:]}
                    }
                    writer.writerow(row)
            
            # Write near misses
            for ticker, reason in near_misses:
                if ticker in stock_metrics:
                    row = {
                        'ticker': ticker,
                        'category': 'NEAR_MISS',
                        'tier': 0,
                        'reason': reason,
                        **{k: stock_metrics[ticker].get(k, '') for k in fieldnames[3:-1]}
                    }
                    writer.writerow(row)
        
        # Also export as JSON for easy programmatic access
        json_file = output_dir / "scan_results.json"
        with open(json_file, 'w') as f:
            json.dump({
                'timestamp': timestamp,
                'recommended_tier1': [t for t in recommended if stock_metrics.get(t, {}).get('tier') == 1],
                'recommended_tier2': [t for t in recommended if stock_metrics.get(t, {}).get('tier') == 2],
                'near_misses': dict(near_misses),
                'metrics': stock_metrics,
                'all_analyzed': all_analyzed
            }, f, indent=2, default=str)
        
        console.print(f"\n[green]✓[/green] Results exported to [cyan]{output_dir}[/cyan]")
        console.print(f"  • All tickers analyzed: [cyan]{all_tickers_file.name}[/cyan]")
        console.print(f"  • Final results summary: [cyan]{final_results_file.name}[/cyan]")
        console.print(f"  • JSON export: [cyan]{json_file.name}[/cyan]")
        
        return str(output_dir)
    
    def scan_earnings(self, input_date: Optional[str] = None, workers: int = 0) -> Tuple[List[str], List[Tuple[str, str]], Dict[str, Dict]]:
        """Main entry point for scanning earnings with enhanced error handling to prevent crashes"""
        
        # Store these parameters as instance variables for use throughout the class
        self.current_input_date = input_date
        
        # Start with empty results in case of early errors
        recommended = []
        near_misses = []
        stock_metrics = {}
        all_analyzed_tickers = {}  # Store all analyzed tickers for CSV export
        
        console.print(Panel.fit("[bold cyan]Starting Earnings Scanner[/bold cyan]", border_style="cyan"))
        
        try:
            # Adjust IV/RV thresholds based on market conditions
            console.print("\n[yellow]Step 1:[/yellow] Checking market conditions...")
            self.adjust_thresholds_based_on_spy()
            
            # Get scan dates with error handling
            console.print("\n[yellow]Step 2:[/yellow] Determining scan dates...")
            try:
                post_date, pre_date = self.get_scan_dates(input_date)
                console.print(f"  • Post-market earnings date: [cyan]{post_date}[/cyan]")
                console.print(f"  • Pre-market earnings date: [cyan]{pre_date}[/cyan]")
            except Exception as e:
                console.print(f"[red]✗ Error getting scan dates: {e}[/red]")
                logger.error(f"Error getting scan dates: {e}")
                return recommended, near_misses, stock_metrics
            
            # Fetch earnings data in parallel with timeout and error handling
            console.print("\n[yellow]Step 3:[/yellow] Fetching earnings data...")
            post_stocks = []
            pre_stocks = []
            
            console.print("  • Data source: [cyan]Investing.com[/cyan]")
            
            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("Fetching earnings data...", total=2)
                    
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        post_future = executor.submit(self.fetch_earnings_data, post_date)
                        pre_future = executor.submit(self.fetch_earnings_data, pre_date)
                        
                        # Get results with timeout to prevent hanging
                        try:
                            post_stocks = post_future.result(timeout=30)  # 30 second timeout
                            progress.update(task, advance=1, description=f"Post-market: {len(post_stocks)} tickers")
                        except Exception as e:
                            console.print(f"[red]✗ Error fetching post-market earnings: {e}[/red]")
                            logger.error(f"Error fetching post-market earnings: {e}")
                            post_stocks = []
                            progress.update(task, advance=1)
                            
                        try:
                            pre_stocks = pre_future.result(timeout=30)  # 30 second timeout
                            progress.update(task, advance=1, description=f"Pre-market: {len(pre_stocks)} tickers")
                        except Exception as e:
                            console.print(f"[red]✗ Error fetching pre-market earnings: {e}[/red]")
                            logger.error(f"Error fetching pre-market earnings: {e}")
                            pre_stocks = []
                            progress.update(task, advance=1)
            except Exception as e:
                console.print(f"[red]✗ Error in parallel processing of earnings data: {e}[/red]")
                logger.error(f"Error in parallel processing of earnings data: {e}")
                # Initialize with empty lists in case of errors
                post_stocks = []
                pre_stocks = []
        except Exception as e:
            console.print(f"[red]✗ Critical error during initialization: {e}[/red]")
            logger.error(f"Error adjusting thresholds or fetching earnings data: {e}")
            return recommended, near_misses, stock_metrics
            
        # Initialize candidates list properly - outside of the try block
        candidates = []
        # Filter candidates (using list comprehensions for speed)
        candidates = [s for s in post_stocks if s['timing'] == 'Post Market'] + \
                     [s for s in pre_stocks if s['timing'] == 'Pre Market']
        
        console.print(f"\n[yellow]Step 4:[/yellow] Filtering candidates...")
        # Show total raw tickers before filtering
        total_raw = len(post_stocks) + len(pre_stocks)
        console.print(f"  • Raw tickers fetched: [cyan]{total_raw}[/cyan]")
        # Show breakdown by timing
        post_market_count = len([s for s in post_stocks if s['timing'] == 'Post Market'])
        pre_market_count = len([s for s in pre_stocks if s['timing'] == 'Pre Market'])
        during_market_count = total_raw - post_market_count - pre_market_count - len([s for s in post_stocks + pre_stocks if s['timing'] == 'Unknown'])
        unknown_count = len([s for s in post_stocks + pre_stocks if s['timing'] == 'Unknown'])
        
        console.print(f"  • Post-market candidates: [cyan]{post_market_count}[/cyan]")
        console.print(f"  • Pre-market candidates: [cyan]{pre_market_count}[/cyan]")
        if during_market_count > 0:
            console.print(f"  • During market (excluded): [dim]{during_market_count}[/dim]")
        if unknown_count > 0:
            console.print(f"  • Unknown timing (excluded): [dim]{unknown_count}[/dim]")
        console.print(f"  • Total candidates to analyze: [bold cyan]{len(candidates)}[/bold cyan]")
        
        logger.info(f"Found {len(candidates)} initial candidates")
        
        recommended = []
        near_misses = []
        stock_metrics = {}
        
        console.print(f"\n[yellow]Step 5:[/yellow] Analyzing stocks...")
        
        # Process in parallel if workers specified
        if workers > 0:
            # Limit max workers for stability (especially with browser operations)
            effective_workers = min(workers, 8)  # Cap at 8 workers max for stability
            console.print(f"  • Processing mode: [cyan]Parallel ({effective_workers} workers)[/cyan]")
            logger.info(f"Using parallel processing with {effective_workers} workers")
            
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                # Submit all stocks for processing
                futures = [executor.submit(self.validate_stock, stock) for stock in candidates]
                
                # Process results as they complete with rich progress bar
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]Analyzing[/bold blue]"),
                    BarColumn(bar_width=40),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TextColumn("•"),
                    TextColumn("[cyan]{task.completed}/{task.total}[/cyan] tickers"),
                    TextColumn("•"),
                    TimeElapsedColumn(),
                    TextColumn("•"),
                    TimeRemainingColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("Processing", total=len(candidates))
                    
                    passed_count = 0
                    near_miss_count = 0
                    failed_count = 0
                    
                    for i, future in enumerate(futures):
                        stock = candidates[i]
                        ticker = stock['ticker']
                        try:
                            result = future.result(timeout=60)  # Add timeout to prevent hanging threads
                            
                            # Store all analyzed tickers
                            all_analyzed_tickers[ticker] = result.get('metrics', {})
                            
                            if result['pass']:
                                recommended.append(ticker)
                                stock_metrics[ticker] = result['metrics']
                                passed_count += 1
                                progress.update(task, advance=1, 
                                              description=f"[green]✓[/green] {ticker} (Pass #{passed_count})")
                            elif result['near_miss']:
                                near_misses.append((ticker, result['reason']))
                                stock_metrics[ticker] = result['metrics']
                                near_miss_count += 1
                                progress.update(task, advance=1, 
                                              description=f"[yellow]~[/yellow] {ticker} (Near miss #{near_miss_count})")
                            else:
                                failed_count += 1
                                progress.update(task, advance=1, 
                                              description=f"[red]✗[/red] {ticker} failed")
                        except Exception as e:
                            failed_count += 1
                            console.print(f"[red]✗ Error processing {ticker}: {e}[/red]")
                            logger.error(f"Error processing {ticker}: {e}")
                            progress.update(task, advance=1)
                    
                    # Final summary in progress
                    progress.update(task, description=f"Complete: {passed_count} passed, {near_miss_count} near, {failed_count} failed")
        else:
            # Original batched sequential processing
            console.print(f"  • Processing mode: [cyan]Sequential (batches of {self.batch_size})[/cyan]")
            batches = [candidates[i:i+self.batch_size] 
                      for i in range(0, len(candidates), self.batch_size)]
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Analyzing[/bold blue]"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("•"),
                TextColumn("[cyan]{task.completed}/{task.total}[/cyan] tickers"),
                TextColumn("•"),
                TimeElapsedColumn(),
                TextColumn("•"),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task("Processing", total=len(candidates))
                
                passed_count = 0
                near_miss_count = 0
                failed_count = 0
                
                for batch_num, batch in enumerate(batches, 1):
                    progress.update(task, description=f"Batch {batch_num}/{len(batches)}")
                    
                    for stock in batch:
                        ticker = stock['ticker']
                        result = self.validate_stock(stock)
                        
                        # Store all analyzed tickers
                        all_analyzed_tickers[ticker] = result.get('metrics', {})
                        
                        if result['pass']:
                            recommended.append(ticker)
                            stock_metrics[ticker] = result['metrics']
                            passed_count += 1
                            progress.update(task, advance=1, 
                                          description=f"[green]✓[/green] {ticker} (Pass #{passed_count})")
                        elif result['near_miss']:
                            near_misses.append((ticker, result['reason']))
                            stock_metrics[ticker] = result['metrics']
                            near_miss_count += 1
                            progress.update(task, advance=1, 
                                          description=f"[yellow]~[/yellow] {ticker} (Near miss #{near_miss_count})")
                        else:
                            failed_count += 1
                            progress.update(task, advance=1, 
                                          description=f"[red]✗[/red] {ticker} failed")
                    
                    if batch != batches[-1]:
                        progress.update(task, description=f"Waiting 5s before next batch...")
                        time.sleep(5)  # Reduced sleep time
                
                # Final summary
                progress.update(task, description=f"Complete: {passed_count} passed, {near_miss_count} near, {failed_count} failed")
        
        # Export results to CSV
        console.print(f"\n[yellow]Step 6:[/yellow] Exporting results...")
        if recommended or near_misses or all_analyzed_tickers:
            self.export_to_csv(stock_metrics, recommended, near_misses, all_analyzed_tickers)
        
        # Print summary
        console.print("\n" + "="*60)
        console.print(Panel.fit(
            f"[bold green]Scan Complete![/bold green]\n\n"
            f"Total Analyzed: [cyan]{len(all_analyzed_tickers)}[/cyan]\n"
            f"Recommended: [green]{len(recommended)}[/green] "
            f"(Tier 1: [green]{len([t for t in recommended if stock_metrics.get(t, {}).get('tier') == 1])}[/green], "
            f"Tier 2: [yellow]{len([t for t in recommended if stock_metrics.get(t, {}).get('tier') == 2])}[/yellow])\n"
            f"Near Misses: [yellow]{len(near_misses)}[/yellow]\n"
            f"Failed: [red]{len(all_analyzed_tickers) - len(recommended) - len(near_misses)}[/red]",
            border_style="green"
        ))
        
        return recommended, near_misses, stock_metrics