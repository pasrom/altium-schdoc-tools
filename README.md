# altium-schdoc-tools

[![Tests](https://github.com/pasrom/altium-schdoc-tools/actions/workflows/tests.yml/badge.svg)](https://github.com/pasrom/altium-schdoc-tools/actions/workflows/tests.yml)

Parse Altium `.SchDoc` schematics into **named netlists** — no Altium licence,
any platform, pure Python on top of [`olefile`](https://pypi.org/project/olefile/).

Given a `.SchDoc` file, these tools answer questions like *"what is connected
to pin 10 of U6?"*, *"which pins are on net SPI_CLK?"*, or *"what does this
sheet do?"* — from the command line, without opening Altium.

## Why this exists

A `.SchDoc` is an OLE compound document whose `FileHeader` stream is a list of
pipe-delimited records — perfectly readable without Altium. The obvious
existing tool, [`a3ng7n/Altium-Schematic-Parser`](https://github.com/a3ng7n/Altium-Schematic-Parser),
breaks on modern Altium exports: it collapses an entire sheet into one
mega-net with every device at `(0,0)` and all net names `null`. Three
independent bugs cause this:

1. **Case-sensitive field names.** Modern Altium writes property keys as
   `Location.X` / `PinConglomerate`; the parser reads `LOCATION.X` /
   `PINCONGLOMERATE` and silently falls back to `0`, so everything "connects"
   at the origin.
2. **OwnerIndex hierarchy drift.** It collects pins by walking the
   `OWNERINDEX` parent hierarchy, but its record numbering differs from the
   file's length-prefix framing, so nearly all pins become unreachable.
3. **Imprecise pin geometry.** The pin's electrical end is computed via
   `cos`/`sin` of a quantised rotation instead of the exact integer formula.

Details, record types and the full format reference:
[docs/altium-schdoc-format.md](docs/altium-schdoc-format.md).

## Two tools, two strengths

| | This repo (`schextract.py` / `schnet.py`) | [pasrom/Altium-Schematic-Parser fork](https://github.com/pasrom/Altium-Schematic-Parser) (`fix/mixed-case-field-names`) |
|---|---|---|
| Output | Text: nets with **designator-level pin lists** (`U6.10(MISO)`) | JSON: named nets + connectivity |
| Net names | Yes (labels, power ports, cross-sheet ports) | Yes — the quick route to a named-net overview |
| Designators | **Resolved** (which pin of which R12/U6) | Not cleanly resolvable from the JSON (only pin numbers / BGA balls) |
| Speed / limits | Geometric union-find is O(points × segments); can **over-merge under dense BGA packages** | `-f net-list` takes minutes per sheet; parts-list mode is fast |

Rule of thumb: **fork** for a fast named-net connectivity overview and JSON
you can post-process; **`schnet.py`** when you need to know *which component
pin* sits on a net. Cross-check one against the other for anything critical.

## Install

```bash
pip install -r requirements.txt   # just olefile
```

## Usage

### Designator-level netlist (this repo)

```bash
# Full netlist of a sheet
python3 schnet.py path/to/Sheet.SchDoc

# Only nets/pins matching a substring (case-insensitive)
python3 schnet.py path/to/Sheet.SchDoc SPI
```

Output shape:

```
NET [SPI_CLK] :: U1.5(SCK), U6.10(CLK), R12.1()
NET [GND / GND_A] :: C3.2(), U1.4(GND), ...
NET [(unnamed)] :: R7.2(), C9.1()
```

```bash
# Record-level summary: components, power ports, net labels, cross-sheet ports
python3 schextract.py path/to/Sheet.SchDoc
```

### Named-net JSON (the fixed fork)

```bash
pip install olefile
git clone -b fix/mixed-case-field-names https://github.com/pasrom/Altium-Schematic-Parser
pip install -e Altium-Schematic-Parser
parse path/to/Sheet.SchDoc -f net-list -o nets.json   # slow: minutes per sheet
```

## Gotchas

- **Cross-sheet nets join by name**, not by any index: parse each sheet
  separately, then merge nets that share a name (net labels, ports, power
  ports).
- **Fit status / DNP is not in the schematic.** Assembly-variant data
  (not-fitted parts, alternates) lives in the project's `.PrjPcb` file. A part
  on the sheet may not be populated on the board.
- **Off-grid placements** carry `_Frac` sub-unit coordinate fields that
  whole-unit parsing ignores; see the
  [format notes](docs/altium-schdoc-format.md).

## Testing

```bash
pip install -r requirements.txt -r requirements-dev.txt
python3 -m pytest tests/ -v
```

Regression tests run both tools against fixtures under `tests/fixtures/` —
public `.SchDoc` files from
[pasrom/Altium-Schematic-Parser](https://github.com/pasrom/Altium-Schematic-Parser)'s
own test suite (MIT-licensed), plus a minimal synthetic case for the
OwnerIndex probe-order logic that none of those fixtures happen to exercise.
The pinned numbers are today's *actual* output, not hand-verified ground
truth — the point is catching a silent regression, which is exactly how the
OwnerIndex fix (see the commit history) got caught in the first place: by
testing against a real schematic, not a synthetic one. CI (GitHub Actions)
runs this on every push against Python 3.9 and 3.12.

## Claude Code skill

The repo ships a Claude Code skill at
[`.claude/skills/altium-schdoc/SKILL.md`](.claude/skills/altium-schdoc/SKILL.md)
that teaches the agent when to reach for which tool and how to avoid the
format traps.

## License

MIT — see [LICENSE](LICENSE).
