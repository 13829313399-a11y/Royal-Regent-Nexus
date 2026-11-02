"""Explicit, reversible format migration using saved snapshots only. No source-data reads."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services import qc_cumulative

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--factory',required=True)
    parser.add_argument('--expected-version',required=True,type=int)
    parser.add_argument('--actor',default='local-cumulative-repair')
    parser.add_argument('--rollback',type=int,help='Repair receipt ID; refused after any subsequent workbook operation')
    args=parser.parse_args()
    result=(qc_cumulative.rollback_repair(args.factory,args.rollback,args.expected_version) if args.rollback is not None
        else qc_cumulative.repair(args.factory,args.actor,args.expected_version))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
