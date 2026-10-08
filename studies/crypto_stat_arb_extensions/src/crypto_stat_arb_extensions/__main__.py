"""Ordered offline research stages. No trading, publication or scheduling."""
import argparse
from pathlib import Path
from .core import DEFAULT_ROOT, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare-history','screen','freeze','evaluate','report','verify','all'])
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    args=parser.parse_args();root=args.root.resolve()
    if args.command in ['prepare-history','all']:
        from .data import prepare_history
        prepare_history(root)
    if args.command in ['screen','all']:
        from .runner import screen_history
        screen_history(root)
    if args.command in ['freeze','all']:
        from .runner import freeze_study
        freeze_study(root)
    if args.command in ['evaluate','all']:
        from .runner import evaluate_holdout
        evaluate_holdout(root)
    if args.command in ['report','all']:
        from .reporting import create_report
        print(create_report(root))
    if args.command=='verify':
        from .runner import verify_results
        print(verify_results(root))


if __name__=='__main__':main()
