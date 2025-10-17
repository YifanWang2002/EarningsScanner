#!/usr/bin/env python3
"""
CLI Scanner for earnings-based options opportunities.
Automatically determines dates based on current time and outputs recommended tickers.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from utils.logging_utils import setup_logging
from core.scanner import EarningsScanner
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console()

def main():
    parser = argparse.ArgumentParser(
        description="""
        Scans for recommended options plays based on upcoming earnings.
        If run before 4PM Eastern: Checks today's post-market and tomorrow's pre-market earnings
        If run after 4PM Eastern: Checks tomorrow's post-market and following day's pre-market earnings
        """
    )
    parser.add_argument(
        '--date', '-d',
        help='Optional date to check in MM/DD/YYYY format (e.g., 03/20/2025). '
             'If not provided, uses current date logic.',
        type=str
    )
    parser.add_argument(
        '--parallel', '-p',
        help='Enable parallel processing with specified number of workers',
        type=int,
        default=0
    )
    parser.add_argument(
        '--list', '-l',
        help='Show compact output with only ticker symbols and tiers',
        action='store_true'
    )
    parser.add_argument(
        '--iron-fly', '-i',
        help='Calculate and display recommended iron fly strikes',
        action='store_true'
    )
    parser.add_argument(
        '--analyze', '-a',
        help='Analyze a specific ticker symbol and display all metrics regardless of pass/fail status',
        type=str,
        metavar='TICKER'
    )
    parser.add_argument(
        '--forever', '-fv',
        help='Repeat scan every N hours (e.g., 1 for hourly scans)',
        type=int
    )
    args = parser.parse_args()
 
    setup_logging(log_dir="logs")
    logger = logging.getLogger(__name__)
    
    input_date = None
    if args.date:
        try:
            input_date = args.date
            datetime.strptime(input_date, '%m/%d/%Y')  # Validate date format
            logger.info(f"Using provided date: {input_date}")
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            sys.exit(1)
    else:
        now = datetime.now(timezone.utc)
        logger.info(f'No date provided. Using current UTC time: '
                    f'{now.strftime("%Y-%m-%d %H:%M:%S %Z")}')

    scanner = EarningsScanner()
    # Check if we're analyzing a specific ticker instead of running a full scan
    if args.analyze:
        ticker = args.analyze.strip().upper()
        console.print(Panel.fit(f"[bold cyan]Analyzing {ticker}[/bold cyan]", border_style="cyan"))
        console.print()

        with console.status(f"[bold blue]Analyzing {ticker}...[/bold blue]", spinner="dots"):
            metrics = scanner.analyze_ticker(ticker)
        
        if 'error' in metrics:
            console.print(f"[red]✗ Error analyzing {ticker}: {metrics['error']}[/red]")
            return

        # Market conditions
        market_table = Table(title="Market Conditions", show_header=False, box=None)
        market_table.add_column("Metric", style="cyan")
        market_table.add_column("Value", style="white")
        market_table.add_row("SPY IV/RV", f"{metrics.get('spy_iv_rv', 0):.2f}")
        market_table.add_row("Pass Threshold", f"{metrics.get('iv_rv_pass_threshold', 1.25):.2f}")
        market_table.add_row("Near Miss Threshold", f"{metrics.get('iv_rv_near_miss_threshold', 1.0):.2f}")
        console.print(market_table)
        console.print()

        # Status
        status = 'PASS' if metrics.get('pass', False) else \
                 ('NEAR MISS' if metrics.get('near_miss', False) else 'FAIL')
        tier_info = ""
        if metrics.get('pass', False) and metrics.get('tier') in (1, 2):
            tier_info = f" - TIER {metrics['tier']}"
        
        status_color = "green" if status == "PASS" else "yellow" if status == "NEAR MISS" else "red"
        console.print(f"[bold {status_color}]Status: {status}{tier_info}[/bold {status_color}]")
        console.print(f"Reason: {metrics.get('reason', 'N/A')}")
        console.print()

        # Core metrics table
        metrics_table = Table(title="Core Metrics", show_header=True)
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", style="white")
        
        if 'price' in metrics:
            metrics_table.add_row("Price", f"${metrics['price']:.2f}")
        if 'volume' in metrics:
            metrics_table.add_row("Volume", f"{metrics['volume']:,.0f}")
        if 'term_structure' in metrics:
            color = "green" if metrics['term_structure'] <= -0.004 else "red"
            metrics_table.add_row("Term Structure", f"[{color}]{metrics['term_structure']:.4f}[/{color}]")
        if 'iv_rv_ratio' in metrics:
            color = "green" if metrics['iv_rv_ratio'] >= metrics.get('iv_rv_pass_threshold', 1.25) else "yellow" if metrics['iv_rv_ratio'] >= metrics.get('iv_rv_near_miss_threshold', 1.0) else "red"
            metrics_table.add_row("IV/RV Ratio", f"[{color}]{metrics['iv_rv_ratio']:.2f}[/{color}]")
        if 'win_rate' in metrics and 'win_quarters' in metrics:
            color = "green" if metrics['win_rate'] >= 50 else "yellow" if metrics['win_rate'] >= 40 else "red"
            metrics_table.add_row("Winrate", f"[{color}]{metrics['win_rate']:.1f}%[/{color}] ({metrics['win_quarters']} earnings)")
        
        console.print(metrics_table)

        # Additional metrics
        extras = {
            k: v for k, v in metrics.items()
            if k not in ('price', 'volume', 'term_structure', 'iv_rv_ratio',
                         'win_rate', 'win_quarters', 'pass', 'near_miss',
                         'tier', 'reason', 'iv_rv_pass_threshold',
                         'iv_rv_near_miss_threshold', 'spy_iv_rv', 'ticker')
        }
        if extras:
            console.print()
            extras_table = Table(title="Additional Metrics", show_header=True)
            extras_table.add_column("Metric", style="cyan")
            extras_table.add_column("Value", style="white")
            for k, v in extras.items():
                if isinstance(v, float):
                    extras_table.add_row(k.replace('_', ' ').title(), f"{v:.4f}")
                else:
                    extras_table.add_row(k.replace('_', ' ').title(), str(v))
            console.print(extras_table)

        if args.iron_fly:
            console.print()
            with console.status("[bold blue]Calculating Iron Fly strategy...[/bold blue]", spinner="dots"):
                iron_fly = scanner.calculate_iron_fly_strikes(ticker)
            
            if 'error' in iron_fly:
                console.print(f"[red]✗ Iron Fly Error: {iron_fly['error']}[/red]")
            else:
                fly_table = Table(title="Iron Fly Strategy", show_header=True)
                fly_table.add_column("Component", style="cyan")
                fly_table.add_column("Details", style="white")
                
                fly_table.add_row("Expiration", iron_fly['expiration'])
                fly_table.add_row("Short Strikes", 
                                f"${iron_fly['short_put_strike']}P / ${iron_fly['short_call_strike']}C")
                fly_table.add_row("Short Credit", f"${iron_fly['total_credit']}")
                fly_table.add_row("Long Strikes", 
                                f"${iron_fly['long_put_strike']}P / ${iron_fly['long_call_strike']}C")
                fly_table.add_row("Long Debit", f"${iron_fly['total_debit']}")
                fly_table.add_row("Net Credit", f"[green]${iron_fly['net_credit']}[/green]")
                fly_table.add_row("Break-evens", 
                                f"${iron_fly['lower_breakeven']} - ${iron_fly['upper_breakeven']}")
                fly_table.add_row("Max Profit", f"[green]${iron_fly['max_profit']}[/green]")
                fly_table.add_row("Max Risk", f"[red]${iron_fly['max_risk']}[/red]")
                fly_table.add_row("Risk/Reward", f"1:{iron_fly['risk_reward_ratio']}")
                
                console.print(fly_table)
        return
        

    try:
        running = True
        while running:
            recommended, near_misses, stock_metrics = scanner.scan_earnings(
                input_date=input_date,
                workers=args.parallel
            )

            if recommended or near_misses:
                console.print()
                console.print(Panel.fit("[bold cyan]SCAN RESULTS[/bold cyan]", border_style="cyan"))
                
                tier1 = [t for t in recommended
                         if stock_metrics[t].get('tier') == 1]
                tier2 = [t for t in recommended
                         if stock_metrics[t].get('tier') == 2]

                if args.list:
                    # Compact list view
                    list_table = Table(show_header=True, box=None)
                    list_table.add_column("Category", style="cyan", width=20)
                    list_table.add_column("Tickers", style="white")
                    
                    list_table.add_row("[green]TIER 1[/green]", ', '.join(tier1) or 'None')
                    list_table.add_row("[yellow]TIER 2[/yellow]", ', '.join(tier2) or 'None')
                    list_table.add_row("[dim]NEAR MISSES[/dim]", 
                                     ', '.join([t for t, _ in near_misses]) or 'None')
                    
                    console.print(list_table)
                else:
                    # Detailed view
                    console.print()
                    
                    # Tier 1 Recommendations
                    console.print("[green bold]TIER 1 RECOMMENDED TRADES:[/green bold]")
                    if tier1:
                        tier1_table = Table(show_header=True, title_style="bold green")
                        tier1_table.add_column("Ticker", style="cyan", width=8)
                        tier1_table.add_column("Price", style="white", width=10)
                        tier1_table.add_column("Volume", style="white", width=12)
                        tier1_table.add_column("Winrate", style="white", width=15)
                        tier1_table.add_column("IV/RV", style="white", width=8)
                        tier1_table.add_column("Term Str", style="white", width=10)
                        
                        for tick in tier1:
                            m = stock_metrics[tick]
                            tier1_table.add_row(
                                f"[bold]{tick}[/bold]",
                                f"${m['price']:.2f}",
                                f"{m['volume']:,.0f}",
                                f"{m['win_rate']:.1f}% ({m['win_quarters']}Q)",
                                f"{m['iv_rv_ratio']:.2f}",
                                f"{m['term_structure']:.3f}"
                            )
                        
                        console.print(tier1_table)
                        
                        # Show iron fly details for each Tier 1 ticker if requested
                        if args.iron_fly:
                            for tick in tier1:
                                with console.status(f"Calculating Iron Fly for {tick}...", spinner="dots"):
                                    fly = scanner.calculate_iron_fly_strikes(tick)
                                if 'error' not in fly:
                                    console.print(f"\n[cyan]{tick} Iron Fly:[/cyan]")
                                    console.print(f"  Short: ${fly['short_put_strike']}P/${fly['short_call_strike']}C "
                                                f"(${fly['total_credit']} credit)")
                                    console.print(f"  Long: ${fly['long_put_strike']}P/${fly['long_call_strike']}C "
                                                f"(${fly['total_debit']} debit)")
                                    console.print(f"  Break-evens: ${fly['lower_breakeven']}-${fly['upper_breakeven']}")
                                    console.print(f"  Risk/Reward: 1:{fly['risk_reward_ratio']}")
                    else:
                        console.print("  [dim]None[/dim]")

                    # Tier 2 Recommendations
                    console.print()
                    console.print("[yellow bold]TIER 2 RECOMMENDED TRADES:[/yellow bold]")
                    if tier2:
                        tier2_table = Table(show_header=True, title_style="bold yellow")
                        tier2_table.add_column("Ticker", style="cyan", width=8)
                        tier2_table.add_column("Price", style="white", width=10)
                        tier2_table.add_column("Volume", style="white", width=12)
                        tier2_table.add_column("Winrate", style="white", width=15)
                        tier2_table.add_column("IV/RV", style="white", width=8)
                        tier2_table.add_column("Term Str", style="white", width=10)
                        
                        for tick in tier2:
                            m = stock_metrics[tick]
                            tier2_table.add_row(
                                f"[bold]{tick}[/bold]",
                                f"${m['price']:.2f}",
                                f"{m['volume']:,.0f}",
                                f"{m['win_rate']:.1f}% ({m['win_quarters']}Q)",
                                f"{m['iv_rv_ratio']:.2f}",
                                f"{m['term_structure']:.3f}"
                            )
                        
                        console.print(tier2_table)
                        
                        # Show iron fly details for Tier 2 if requested
                        if args.iron_fly:
                            for tick in tier2:
                                with console.status(f"Calculating Iron Fly for {tick}...", spinner="dots"):
                                    fly = scanner.calculate_iron_fly_strikes(tick)
                                if 'error' not in fly:
                                    console.print(f"\n[cyan]{tick} Iron Fly:[/cyan]")
                                    console.print(f"  Short: ${fly['short_put_strike']}P/${fly['short_call_strike']}C "
                                                f"(${fly['total_credit']} credit)")
                                    console.print(f"  Long: ${fly['long_put_strike']}P/${fly['long_call_strike']}C "
                                                f"(${fly['total_debit']} debit)")
                                    console.print(f"  Break-evens: ${fly['lower_breakeven']}-${fly['upper_breakeven']}")
                                    console.print(f"  Risk/Reward: 1:{fly['risk_reward_ratio']}")
                    else:
                        console.print("  [dim]None[/dim]")

                    # Near Misses
                    console.print()
                    console.print("[dim bold]NEAR MISSES:[/dim bold]")
                    if near_misses:
                        nm_table = Table(show_header=True, title_style="dim")
                        nm_table.add_column("Ticker", style="cyan", width=8)
                        nm_table.add_column("Reason", style="red", width=30)
                        nm_table.add_column("Price", style="white", width=10)
                        nm_table.add_column("Volume", style="white", width=12)
                        nm_table.add_column("Winrate", style="white", width=15)
                        nm_table.add_column("IV/RV", style="white", width=8)
                        nm_table.add_column("Term Str", style="white", width=10)
                        
                        for tick, reason in near_misses:
                            m = stock_metrics[tick]
                            nm_table.add_row(
                                f"[bold]{tick}[/bold]",
                                reason[:28] + "..." if len(reason) > 30 else reason,
                                f"${m['price']:.2f}",
                                f"{m['volume']:,.0f}",
                                f"{m['win_rate']:.1f}% ({m['win_quarters']}Q)",
                                f"{m['iv_rv_ratio']:.2f}",
                                f"{m['term_structure']:.3f}"
                            )
                        
                        console.print(nm_table)
                    else:
                        console.print("  [dim]None[/dim]")
            
            else:
                console.print("\n[yellow]No recommended stocks found in this scan.[/yellow]")
                logger.info('No recommended stocks found')

            if args.forever and args.forever > 0:
                logger.info(f'Sleeping for {args.forever} hours...')
                time.sleep(args.forever * 3600)
            else:
                running = False

    except KeyboardInterrupt:
        logger.info('Interrupted; exiting.')
    except ValueError as e:
        logger.error(f'Error: {e}')

if __name__ == '__main__':
    main()
