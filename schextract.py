#!/usr/bin/env python3
"""Extract Altium .SchDoc records via olefile. Designator-resolved.

Reads the FileHeader stream of an Altium .SchDoc (OLE compound document),
parses the length-prefixed pipe-delimited records, and prints a summary:
components (with designators), power ports, net labels and cross-sheet ports.

Usage: python3 schextract.py <path/to/sheet.SchDoc>
"""
import olefile, sys, struct

def read_records(path):
    ole = olefile.OleFileIO(path)
    # FileHeader stream
    if not ole.exists('FileHeader'):
        # find stream
        for s in ole.listdir():
            if 'FileHeader' in s:
                data = ole.openstream(s).read()
                break
        else:
            raise RuntimeError("no FileHeader")
    else:
        data = ole.openstream('FileHeader').read()
    ole.close()
    recs = []
    i = 0
    n = len(data)
    while i + 4 <= n:
        length = struct.unpack('<I', data[i:i+4])[0]
        i += 4
        if length == 0 or i + length > n:
            break
        payload = data[i:i+length]
        i += length
        # strip trailing NUL
        if payload.endswith(b'\x00'):
            payload = payload[:-1]
        try:
            s = payload.decode('latin-1')
        except:
            s = ''
        recs.append(s)
    return recs

def parse_fields(s):
    d = {}
    for tok in s.split('|'):
        if '=' in tok:
            k, _, v = tok.partition('=')
            d[k.upper()] = v  # upper-fold keys
    return d

def main(path):
    recs = read_records(path)
    parsed = [parse_fields(r) for r in recs]
    # Build component index -> designator/comment
    # records of RECORD=1 are components; their designator is a child RECORD=34 with OwnerIndex
    comp_by_idx = {}  # ordinal index -> dict
    for idx, d in enumerate(parsed):
        if d.get('RECORD') == '1':
            comp_by_idx[idx] = {
                'libref': d.get('LIBREFERENCE',''),
                'comment': d.get('COMMENT',''),
                'designator': '?',
                'idx': idx,
            }
    # designators (record 34) and params (41) attach via OWNERINDEX
    for idx, d in enumerate(parsed):
        if d.get('RECORD') == '34':
            oi = d.get('OWNERINDEX')
            if oi is not None:
                try:
                    oidx = int(oi)
                except:
                    continue
                # owner ordinal: OwnerIndex+1 is the documented convention
                # (records list, header is index 0); OwnerIndex/OwnerIndex-1
                # are fallbacks for older exports. Same order as schnet.py.
                for cand in (oidx+1, oidx, oidx-1):
                    if cand in comp_by_idx:
                        comp_by_idx[cand]['designator'] = d.get('TEXT', comp_by_idx[cand]['designator'])
                        break
    # also capture COMMENT from record 41 Parameter with NAME=Comment? Often comment on rec 1.
    print(f"### FILE: {path}")
    print(f"# total records: {len(recs)}")
    # Components
    print("\n## COMPONENTS (designator | libref | comment)")
    comps = sorted(comp_by_idx.values(), key=lambda c: c['designator'])
    for c in comps:
        print(f"  {c['designator']:>8} | {c['libref']:<28} | {c['comment']}")
    # Power ports (17)
    print("\n## POWER PORTS (net names)")
    pp = set()
    for d in parsed:
        if d.get('RECORD') == '17':
            pp.add(d.get('TEXT',''))
    for t in sorted(pp):
        print(f"  PWR: {t}")
    # Net labels (25)
    print("\n## NET LABELS")
    nl = {}
    for d in parsed:
        if d.get('RECORD') == '25':
            t = d.get('TEXT','')
            nl[t] = nl.get(t,0)+1
    for t in sorted(nl):
        print(f"  NET: {t} (x{nl[t]})")
    # Ports (18) cross-sheet
    print("\n## PORTS (cross-sheet)")
    pt = set()
    for d in parsed:
        if d.get('RECORD') == '18':
            pt.add(d.get('NAME',''))
    for t in sorted(pt):
        print(f"  PORT: {t}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: python3 schextract.py <path/to/sheet.SchDoc>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
