"""Export the same catalog offered by Help > Icons & artwork. No network."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from utterleaf.brand_export import asset_catalog

def main():
    out=ROOT/'docs/assets/brand'
    out.mkdir(parents=True,exist_ok=True)
    count=0
    for name,data in asset_catalog():
        (out/name).write_bytes(data)
        if name=='utterleaf.ico':
            (ROOT/'packaging'/name).write_bytes(data)
        count+=1
    print(f'Exported {count} assets and usage manifest to {out}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
