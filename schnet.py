#!/usr/bin/env python3
"""Build named netlist from Altium .SchDoc via geometric connectivity.

Union-find over pin/label/port/wire coordinates; a pin's electrical end is
Location + PinLength * dir(PinConglomerate & 3). Prints each net with its
name(s) and designator-level pin members.

Usage: python3 schnet.py <path/to/sheet.SchDoc> [filter]
"""
import sys
import schextract as se

DIRS = [(1,0),(0,1),(-1,0),(0,-1)]  # PinConglomerate & 3

def to_i(v, d=0):
    try: return int(v)
    except:
        try: return int(float(v))
        except: return d

class UF:
    def __init__(self): self.p={}
    def find(self,x):
        self.p.setdefault(x,x)
        while self.p[x]!=x:
            self.p[x]=self.p[self.p[x]]; x=self.p[x]
        return x
    def union(self,a,b):
        ra,rb=self.find(a),self.find(b)
        if ra!=rb: self.p[ra]=rb

def on_segment(px,py,x1,y1,x2,y2):
    # collinear & within bbox (axis-aligned segments mostly)
    if x1==x2:
        return px==x1 and min(y1,y2)<=py<=max(y1,y2)
    if y1==y2:
        return py==y1 and min(x1,x2)<=px<=max(x1,x2)
    # diagonal: parametric
    cross=(x2-x1)*(py-y1)-(y2-y1)*(px-x1)
    if cross!=0: return False
    return min(x1,x2)<=px<=max(x1,x2) and min(y1,y2)<=py<=max(y1,y2)

def build(path):
    recs=se.read_records(path)
    P=[se.parse_fields(r) for r in recs]
    # components
    comp={}
    for i,d in enumerate(P):
        if d.get('RECORD')=='1':
            comp[i]={'libref':d.get('LIBREFERENCE',''),'designator':'?','idx':i}
    for i,d in enumerate(P):
        if d.get('RECORD')=='34':
            oi=to_i(d.get('OWNERINDEX'),-99)
            for c in (oi+1,oi,oi-1):
                if c in comp:
                    comp[c]['designator']=d.get('TEXT',comp[c]['designator']); break
    # nodes: list of (id, x, y, kind, label)
    nodes=[]
    pinnode={}  # nodeid -> (designator, pinname, pinnum)
    labelnode={} # nodeid -> netname
    # pins
    for i,d in enumerate(P):
        if d.get('RECORD')=='2':
            oi=to_i(d.get('OWNERINDEX'),-99)
            owner=None
            for c in (oi+1,oi,oi-1):
                if c in comp: owner=comp[c]; break
            x=to_i(d.get('LOCATION.X')); y=to_i(d.get('LOCATION.Y'))
            plen=to_i(d.get('PINLENGTH'))
            conglom=to_i(d.get('PINCONGLOMERATE'))
            dx,dy=DIRS[conglom&3]
            tx,ty=x+dx*plen, y+dy*plen
            nid=('pin',i)
            nodes.append((nid,tx,ty))
            des=owner['designator'] if owner else '?'
            pinnode[nid]=(des, d.get('NAME',''), d.get('DESIGNATOR',''), owner['libref'] if owner else '')
    # power ports (17) - connect point at location
    for i,d in enumerate(P):
        if d.get('RECORD')=='17':
            x=to_i(d.get('LOCATION.X')); y=to_i(d.get('LOCATION.Y'))
            nid=('pwr',i); nodes.append((nid,x,y)); labelnode[nid]=('PWR',d.get('TEXT',''))
    # net labels (25)
    for i,d in enumerate(P):
        if d.get('RECORD')=='25':
            x=to_i(d.get('LOCATION.X')); y=to_i(d.get('LOCATION.Y'))
            nid=('net',i); nodes.append((nid,x,y)); labelnode[nid]=('NET',d.get('TEXT',''))
    # ports (18)
    for i,d in enumerate(P):
        if d.get('RECORD')=='18':
            x=to_i(d.get('LOCATION.X')); y=to_i(d.get('LOCATION.Y'))
            nid=('port',i); nodes.append((nid,x,y)); labelnode[nid]=('PORT',d.get('NAME',''))
    # wires (27): segments; each vertex is a node; consecutive vertices connected
    wsegs=[]  # (x1,y1,x2,y2)
    wirevtx=[] # nodes for wire vertices
    for i,d in enumerate(P):
        if d.get('RECORD')=='27':
            lc=to_i(d.get('LOCATIONCOUNT'))
            pts=[]
            for k in range(1,lc+1):
                xk=to_i(d.get(f'X{k}')); yk=to_i(d.get(f'Y{k}'))
                pts.append((xk,yk))
            for k in range(len(pts)-1):
                wsegs.append((i,k,pts[k][0],pts[k][1],pts[k+1][0],pts[k+1][1]))
    # junctions (29) optional - treat as points
    # Union-find over node ids + wire-segment ids
    uf=UF()
    # index nodes by coordinate for quick equal-point merge
    from collections import defaultdict
    bycoord=defaultdict(list)
    for nid,x,y in nodes:
        bycoord[(x,y)].append(nid)
    # merge coincident nodes
    for pts,lst in bycoord.items():
        for j in range(1,len(lst)):
            uf.union(lst[0],lst[j])
    # wire segments: union the two endpoints of each segment under a seg id, and
    # connect segment endpoints that share a coordinate
    segbycoord=defaultdict(list)
    for (wi,k,x1,y1,x2,y2) in wsegs:
        sid=('seg',wi,k)
        uf.union(sid,sid)
        segbycoord[(x1,y1)].append(sid)
        segbycoord[(x2,y2)].append(sid)
    # connect segments sharing endpoints
    for pts,lst in segbycoord.items():
        for j in range(1,len(lst)):
            uf.union(lst[0],lst[j])
    # connect each node to any wire segment whose body touches it (endpoint or on-segment)
    for nid,x,y in nodes:
        for (wi,k,x1,y1,x2,y2) in wsegs:
            if on_segment(x,y,x1,y1,x2,y2):
                uf.union(nid,('seg',wi,k))
    # Build nets
    from collections import defaultdict
    netmembers=defaultdict(list)
    netnames=defaultdict(set)
    for nid,x,y in nodes:
        r=uf.find(nid)
        if nid in pinnode:
            netmembers[r].append(pinnode[nid])
        if nid in labelnode:
            netnames[r].add(labelnode[nid])
    return comp, netmembers, netnames, pinnode

def main(path, filt=None):
    comp,netmembers,netnames,pinnode=build(path)
    print(f"### NETLIST: {path}")
    nets=[]
    for r,members in netmembers.items():
        names=netnames.get(r,set())
        named=[n for (k,n) in names if k in ('PWR','NET','PORT') and n]
        netlabel=' / '.join(sorted(set(named))) if named else '(unnamed)'
        nets.append((netlabel, members, names))
    nets.sort(key=lambda t:t[0])
    for netlabel,members,names in nets:
        if filt and filt.lower() not in (netlabel+' '+' '.join(f"{d}.{p}" for d,p,n,l in members)).lower():
            continue
        mlist=', '.join(f"{d}.{num}({p})" for d,p,num,l in sorted(members))
        print(f"\nNET [{netlabel}] :: {mlist}")

if __name__=='__main__':
    if len(sys.argv) < 2:
        print("usage: python3 schnet.py <path/to/sheet.SchDoc> [filter]", file=sys.stderr)
        sys.exit(2)
    filt=sys.argv[2] if len(sys.argv)>2 else None
    main(sys.argv[1], filt)
