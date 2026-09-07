---
name: altium-schdoc
description: Parses Altium .SchDoc schematics into named netlists without an Altium licence, using olefile-based tools from the altium-schdoc-tools repo. Use when the user hands over a .SchDoc file and asks what is connected to a pin, to trace a net, to extract a netlist, or to explain what a schematic does. Triggers on Altium, SchDoc, schematic, netlist, trace net, pin connections, Altium Schaltplan, Netzliste, Schaltplan interpretieren, Netzliste extrahieren.
---

# Altium .SchDoc netlist extraction

Turns an Altium `.SchDoc` (binary OLE file, unreadable as text) into a named
netlist you can reason about: which pins sit on which net, what a sheet does,
whether a datasheet claim matches the wiring. No Altium needed; KiCad tooling
cannot open these files either.

## Prerequisite: run from a local clone

The commands below run `schnet.py` / `schextract.py` from the **repo root of
a local clone of `pasrom/altium-schdoc-tools`**. Installed as a plugin, only
this file travels — not the scripts. So before the first command:

1. Find the clone. Ask the user if you don't know it (a common spot is
   `~/git/altium-schdoc-tools`, but do not assume it).
2. Confirm the dependency: `python3 -c "import olefile"` must succeed;
   otherwise `pip install -r requirements.txt` there.

## Which tool for which question

Two engines, complementary — pick by what the question needs:

| Question | Tool |
|---|---|
| "Which pins of which components are on net X?" / "What is connected to U6 pin 10?" | **`schnet.py`** (this repo) — designator-level pin lists |
| "Give me the net names / connectivity overview as JSON" | **Fixed fork** [`pasrom/Altium-Schematic-Parser`](https://github.com/pasrom/Altium-Schematic-Parser), branch `fix/mixed-case-field-names` — named nets, but designators are NOT cleanly resolvable from its JSON |
| "What parts are on this sheet?" / quick orientation | **`schextract.py`** — components, power ports, net labels, cross-sheet ports |

Do NOT use the upstream `a3ng7n/Altium-Schematic-Parser` from PyPI: on modern
Altium exports it collapses the whole sheet into one mega-net (three bugs, see
[docs/altium-schdoc-format.md](../../../docs/altium-schdoc-format.md)). Only
the fork's fix branch works.

## TL;DR: designator-level nets (this repo)

```bash
cd <clone of altium-schdoc-tools>
python3 schextract.py /path/to/Sheet.SchDoc          # orient: parts, net names
python3 schnet.py /path/to/Sheet.SchDoc              # full netlist
python3 schnet.py /path/to/Sheet.SchDoc SPI          # filter nets/pins by substring
```

Output lines look like `NET [SPI_CLK] :: U1.5(SCK), U6.10(CLK), R12.1()` —
designator.pinnumber(pinname).

## TL;DR: named-net JSON (the fork)

```bash
pip install olefile
git clone -b fix/mixed-case-field-names https://github.com/pasrom/Altium-Schematic-Parser
pip install -e Altium-Schematic-Parser
parse /path/to/Sheet.SchDoc -f net-list -o nets.json
```

## Gotchas that will bite you

- **`-f net-list` is slow** — minutes per sheet (geometric connectivity is
  ~O(points × segments)). Start it, work on something else, don't assume it
  hung. `schnet.py` is usually quicker on a single sheet.
- **Over-merge under dense BGAs.** `schnet.py`'s geometric union-find can
  merge distinct nets under a large BGA (many pins on a tight grid). Discrete
  and connector nets come out exact. For anything under a big BGA, cross-check
  against the fork's named-net JSON before drawing conclusions.
- **Field-name casing.** Modern Altium writes `Location.X`/`PinConglomerate`;
  older files write `LOCATION.X`. Both tools here upper-fold keys, so this is
  handled — but if you ever parse records by hand, never match keys
  case-sensitively.
- **`_Frac` sub-units.** Off-grid placements carry fractional coordinate
  fields (`Location.X_Frac`, 1/100000 units) that whole-unit parsing ignores.
  If a net is broken where the drawing clearly connects, suspect this.
- **Cross-sheet nets join by NAME, not OwnerIndex.** Parse each sheet
  separately, then merge nets sharing a name (net labels, ports, power ports).
  There is no cross-sheet index to follow.
- **Fit status / DNP is not in the `.SchDoc`.** Not-fitted parts and assembly
  variants live in the project's `.PrjPcb` (`[ProjectVariant…] Variation …
  Kind=1`). Never claim a part is populated from the schematic alone.

## Interpreting results

- `(unnamed)` nets are real local nets with no label — normal for two-pin
  RC/divider nodes.
- A designator of `?` means the pin's owning component could not be resolved
  via `OwnerIndex` (rare with this parser; more common in damaged exports).
- Multiple names on one net (`GND / GND_A`) mean labels/ports with different
  names touch the same copper — worth flagging, sometimes intentional
  (star-point ties), sometimes a finding.

## Deep format reference

OLE structure, record framing, record-type table, the exact pin hot-end
formula and the OwnerIndex convention:
[docs/altium-schdoc-format.md](../../../docs/altium-schdoc-format.md) in this
repo. Read it before parsing records by hand or debugging a broken net.
