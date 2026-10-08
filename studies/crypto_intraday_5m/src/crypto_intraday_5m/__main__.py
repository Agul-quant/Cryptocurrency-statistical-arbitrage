"""Local educational research only; no exchange orders or monitoring."""
import argparse
from pathlib import Path
from .core import DEFAULT_ROOT,load_config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['download','run','verify','report','all'])
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    args=parser.parse_args();root=args.root.resolve();config=load_config(root)
    if args.command in ['download','all']:
        from .data import download_and_prepare
        print(download_and_prepare(root,config))
    if args.command in ['run','all']:
        from .runner import run_research
        print(run_research(root))
    if args.command in ['verify']:
        from .runner import verify_results
        print(verify_results(root))
    if args.command in ['report','all']:
        from .reporting import create_report
        print(create_report(root))


if __name__=='__main__':main()
