#!/usr/bin/env python3
"""Run the fixed development, validation and partial-year OOS comparisons offline."""
import argparse
from pathlib import Path
import sys
import subprocess
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from crypto_research.runner import evaluate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'local_outputs/reproduction')
    p.add_argument('--all-scenarios',action='store_true',help='Six fee levels at lag1, plus 20bps at lag2')
    p.add_argument('--strategy',action='append',dest='ids',help='Restrict to named frozen strategy; repeatable')
    p.add_argument('--period',action='append',dest='periods',choices=('development','validation','oos_partial_2026_jan_sep'))
    a=p.parse_args()
    subprocess.run([sys.executable,str(ROOT/'scripts/verify_project.py')],cwd=ROOT,check=True)
    evaluate(ROOT,a.output,all_scenarios=a.all_scenarios,ids=a.ids,periods=a.periods)
if __name__=='__main__':main()
