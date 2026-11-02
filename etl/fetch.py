import argparse
from etl.archive import fetch_month
if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('months',nargs='+');a=p.parse_args()
    for month in a.months: print(fetch_month(month),flush=True)
