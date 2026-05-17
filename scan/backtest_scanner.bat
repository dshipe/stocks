# Default: 1 year, S&P 500 only (~2-3 min)
python backtest_scanner.py

# 2 years, full Nasdaq universe (~20-30 min)
python backtest_scanner.py --years 1.5 --universe full

# 1 year, A/A+ grades only in the CSV output
python backtest_scanner.py --min-grade A

# Custom output path
python backtest_scanner.py --output backtest.csv

pause