#!/usr/bin/env python3
"""Reconcile joint basket models and coin-attribution intervals from saved daily inputs."""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from crypto_research.diagnostics import reproduce
from crypto_research.output_safety import checked_output_path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'local_outputs/diagnostic_reproduction.json')
    args=parser.parse_args()
    output=checked_output_path(ROOT,args.output)
    result=reproduce(ROOT)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['numeric_checks','maximum_absolute_errors','model_sample_and_reliability','bootstrap']},indent=2,sort_keys=True))
    print('Detailed reconciliation:',output)

if __name__=='__main__':main()
