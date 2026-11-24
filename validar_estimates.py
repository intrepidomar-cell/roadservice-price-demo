"""Local CLI: no external connections, no DB writes. Does not print PII or notes."""
import argparse
from pathlib import Path
from core.invoice_router import read_invoice


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths',nargs='+',type=Path)
    args=parser.parse_args(); failed=0; count=0
    for p in args.paths:
        files=sorted(x for x in p.rglob('*') if x.is_file() and x.suffix.lower()=='.pdf') if p.is_dir() else [p]
        for f in files:
            count+=1
            try:
                d=read_invoice(f)
                total=next((v for k,v in d.summary.items() if k.lower() in ('total','invoice total','invoiced total','estimate total')),None)
                print(f'{f.name} | {d.reader} | {len(d.items)} rows | total={total} | type={d.document_type}')
                for k,v in d.checks.items(): print(f'  {k}: delta={v}')
                print(f'  Warnings: {len(d.warnings)}')
                if d.reader=='unsupported' or not d.items or total is None or any(v is None or abs(v)>0.02 for v in d.checks.values()): failed+=1
            except Exception as exc:
                print(f'{f.name}: ERROR ({type(exc).__name__})'); failed+=1
    print(f'Checked {count} file(s); {failed} need review. No DB writes.')
    return int(failed>0 or count==0)

if __name__=='__main__': raise SystemExit(main())
