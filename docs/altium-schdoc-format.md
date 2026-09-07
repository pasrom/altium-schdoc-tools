# Altium .SchDoc file format notes

What you need to know to parse an Altium `.SchDoc` schematic without Altium.
This is the reference behind `schextract.py` / `schnet.py` and behind the fixes
in the [pasrom/Altium-Schematic-Parser](https://github.com/pasrom/Altium-Schematic-Parser)
fork (branch `fix/mixed-case-field-names`).

## OLE container

- A `.SchDoc` is an **OLE compound document** (the same container format as
  legacy `.doc`/`.xls`). Open it with [`olefile`](https://pypi.org/project/olefile/);
  the schematic content lives in the **`FileHeader`** stream.
- The stream is a sequence of records:

  ```
  [u32 little-endian length][payload, ends with a trailing NUL]
  ```

  The payload decodes as **latin-1** and is a **pipe-delimited** key/value
  string: `|KEY=VALUE|KEY=VALUE|…`. Records in practice stay under 64 KB, so a
  u16 read of the length happens to work, but the field is really u32 — read
  4 bytes.

## Record types

| RECORD | Meaning |
|---|---|
| 1  | Component (`LibReference`, `Comment`) |
| 2  | Pin (`Location.X/Y`, `PinLength`, `PinConglomerate`, `Name`, `Designator` = pin number) |
| 17 | Power port (`Text` = net name, e.g. GND, VCC) |
| 18 | Cross-sheet port (`Name` = net name) |
| 25 | Net label (`Text` = net name) |
| 27 | Wire (`LocationCount`, `X1/Y1 .. Xn/Yn` polyline vertices) |
| 29 | Junction (a point; optional for connectivity if wires are parsed as segments) |
| 34 | Designator (`Text` = "R12", attaches to its component via `OwnerIndex`) |
| 41 | Parameter (`Name`/`Text` pairs, e.g. `=Value`; attaches via `OwnerIndex`) |

## The field-name casing trap

`RECORD` and `HEADER` are always upper-case, but the **property keys changed
casing between Altium generations**:

- Older exports: screaming caps — `LOCATION.X`, `OWNERINDEX`, `PINLENGTH`.
- Modern exports: PascalCase/dotted — `Location.X`, `OwnerIndex`,
  `PinConglomerate`, `PinLength`, `Text`, `Name`, `Designator`, `LibReference`.

A parser that does a case-sensitive `dict.get('LOCATION.X', 0)` on a modern
file silently reads every coordinate as `0` — every pin, port and label then
"connects" at the origin and the whole sheet collapses into one mega-net.
**Upper-fold all keys at ingestion** (values untouched); that is
version-agnostic and what both tools here do.

## Pin geometry: where a pin actually connects

A pin's stored `Location` is the **body** end. The electrically hot end (the
one that touches a wire) is:

```
hot_end = Location + PinLength * dir(PinConglomerate & 3)
dir: 0 = (+x), 1 = (+y), 2 = (-x), 3 = (-y)
```

Integer math, no trigonometry. (Computing the tip via `cos`/`sin` of a
quantised rotation is imprecise and one of the failure modes of the public
parser.) Empirically, on a dense sheet the large majority of pins land
exactly on a wire vertex or segment this way; the rest connect at exact
coordinates to power ports, net labels or other pins.

## OwnerIndex convention

Child records (pin 2, designator 34, parameter 41) reference their component
via `OwnerIndex`. **The mapping depends on how you split the stream into
records.** With the length-prefix parse above, the owning component sits at
ordinal `OwnerIndex + 1` (record 0 is the file header). A tool that splits
records differently (e.g. on a 5-byte signature) numbers them differently and
its `OwnerIndex` hierarchy drifts — child records then attach to the wrong or
no component. `schextract.py`/`schnet.py` probe `OwnerIndex+1`, `OwnerIndex`,
`OwnerIndex-1` in that order to tolerate both conventions.

Connectivity itself never needs `OwnerIndex`: it is purely geometric.
`OwnerIndex` is only needed to resolve **designators** (which pin belongs to
which "R12").

## Off-grid placements: `_Frac` sub-units

Coordinates can carry fractional sub-unit fields, e.g. `Location.X_Frac`
(units of 1/100000). Whole-unit parsing ignores them — fine for grid-aligned
sheets, wrong for off-grid placements. If nets come out broken where the
drawing clearly connects, check for `_Frac` keys on the pins involved.

## Multi-part components: the same designator, drawn twice

Verified against a real production schematic (not a synthetic fixture): a
large, high-pin-count component was drawn as **two separate `RECORD=1`
component instances**, each with its own `RECORD=34` designator record
carrying the *same* text (e.g. both say `U1`), and in this case the two
instances even shared a pin number. This is a real, legitimate Altium
pattern for large parts split across multiple graphical blocks on a sheet
for readability, and Altium's own netlist compiler treats
same-designator/same-pin-number instances as one physical pin regardless of
geometry.

`schnet.py`'s model does not know this: it treats the two `RECORD=1`
instances as two independent components. If one instance's copy of the pin
is wired on the sheet and the other's is not, the wired one lands correctly
in its net and the unwired one comes out as its own disconnected, unnamed
single-pin "net" — even though electrically it is the same pin. Symptom:
a real net shows the expected members *and* one or more suspicious
single-pin `(unnamed)` nets naming a pin that also appears, correctly, in a
larger named net. If you see that pattern, check for a second `RECORD=34`
with the same designator text before concluding the pin is actually
floating.

## What is NOT in the .SchDoc

- **Fit status (not-fitted / DNP) and assembly-variant alternates** live in
  the project file (`.PrjPcb`), in the assembly-variant data
  (`[ProjectVariant…] Variation … Kind=1`) — **not** on the schematic sheet.
  A part shown on the sheet may not be populated on the board you are
  analysing.
- **Cross-sheet connectivity.** Nets join across sheets **by name** (net
  labels, ports, power ports), not by any index. Parse each sheet separately,
  then merge nets that share a name.

## The three bugs in the public a3ng7n parser

[`a3ng7n/Altium-Schematic-Parser`](https://github.com/a3ng7n/Altium-Schematic-Parser)
(`pip install altium-schematic-parser`) is the obvious existing tool, but on
modern Altium exports its `-f net-list` output collapses the whole sheet into
a single mega-net (every device at `coords [[0,0]]`, all net names `null`).
Three independent defects:

1. **Case-sensitive field names.** It reads `LOCATION.X`/`PINCONGLOMERATE`/…
   (upper), modern files use `Location.X`/`PinConglomerate`; the case-sensitive
   fallback-to-0 puts every pin/port/label at the origin. (Wires survive —
   they are read via a regex on the real `X1/Y1` keys.)
2. **Net-list walks the `OWNERINDEX` hierarchy** to collect pins, but its
   5-byte-signature record split numbers records differently than the
   length-prefix framing, so the hierarchy drifts and nearly all pins become
   unreachable children.
3. **Pin hot-end computed via `cos`/`sin`** of a quantised rotation —
   imprecise; the integer formula above is exact.

The fix, forked and verified at
[pasrom/Altium-Schematic-Parser](https://github.com/pasrom/Altium-Schematic-Parser)
branch `fix/mixed-case-field-names`:

- upper-fold all record keys at ingestion (version-agnostic, values untouched);
- collect net devices from a flat, index-tagged record list instead of the
  hierarchy (connectivity is geometric and needs no `OwnerIndex`);
- integer pin-tip geometry `Location + PinLength * dir(PinConglomerate & 3)`;
- populate net names from net-label (25) / power-port (17) `Text` and port
  (18) `Name`, and unify same-named nodes so global nets (GND, supply rails)
  span the sheet.

Verified on a real, dense multi-sheet production design: the fix correctly
resolved the sheet into per-net groups, spot-checked nets exact, no
regression on older uppercase-key files or on `-f parts-list`. Reproducible
with public files: the fork's own test fixtures under `tests/altium_crap/`
(e.g. `MAX1229_CurrentSense.SchDoc`, 8 components) parse cleanly into 36
nets, 3 of them named, with both tools here — check it yourself against
files anyone can download.

## Known limits

- `-f net-list` in the fork is **slow** (minutes per sheet — geometric
  connectivity is roughly O(points × segments)). Same complexity class in
  `schnet.py`, which is typically quicker in practice on a single sheet.
- The naive geometric union-find in `schnet.py` can **over-merge nets under
  dense BGA packages** (many pins on a tight grid). Discrete-logic and
  connector nets come out exact; treat nets under a large BGA with suspicion
  and cross-check against the fork's named-net output.
- The fork's JSON has correct net names and connectivity, but **component
  designators are not cleanly resolvable** from it (the `OwnerIndex` drift
  again; only pin numbers / BGA balls come out). For designator-level pin
  lists use `schnet.py`.
