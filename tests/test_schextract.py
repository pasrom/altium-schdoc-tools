"""Regression tests for schextract.py against public fixture schematics.

Fixtures under tests/fixtures/ come from pasrom/Altium-Schematic-Parser's own
test suite (tests/altium_crap/), MIT-licensed, chosen for size and variety
rather than for being "correct" in any verified sense: nobody has hand-checked
these against Altium itself. These tests pin today's *actual* behavior so a
future change that silently breaks record parsing or designator resolution
gets caught - not a claim that the pinned numbers are ground truth.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schextract as se

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# path -> (records, components, unresolved_designators, power_ports, net_labels)
EXPECTED = {
    "16bit_ripple_adder.SchDoc": (227, 4, 0, 0, 16),
    "basic_power_supply.SchDoc": (400, 12, 0, 1, 5),
    "max1229_currentsense.SchDoc": (429, 8, 6, 2, 0),
}


def _resolve_designators(records):
    # Calls the real implementation in schextract.py - a test with its own
    # duplicate of this logic would happily stay green while the actual
    # probe-order regression (see the fix commit) went uncaught.
    parsed = [se.parse_fields(r) for r in records]
    return parsed, se.resolve_designators(parsed)


def test_owner_index_plus_one_probed_first():
    # Targeted regression for the OwnerIndex probe-order bug: two components
    # at adjacent ordinals, a designator record whose OwnerIndex points at
    # the FIRST one, so OwnerIndex+1 (the documented, correct convention)
    # resolves to the SECOND. None of the public fixtures happen to exercise
    # this adjacency, so it needs its own minimal case - confirmed by
    # reverting the fix locally and watching this fail while the
    # fixture-based tests below stayed green.
    records = [
        "RECORD=1|LIBREFERENCE=PART_A",
        "RECORD=1|LIBREFERENCE=PART_B",
        "RECORD=34|OWNERINDEX=0|TEXT=B_DESIGNATOR",
    ]
    parsed = [se.parse_fields(r) for r in records]
    comp_by_idx = se.resolve_designators(parsed)
    assert comp_by_idx[1]["designator"] == "B_DESIGNATOR"
    assert comp_by_idx[0]["designator"] == "?"


def test_all_fixtures_present():
    found = {os.path.basename(p) for p in glob.glob(os.path.join(FIXTURES_DIR, "*.SchDoc"))}
    assert found == set(EXPECTED), f"fixture set changed: {found} != {set(EXPECTED)}"


def test_fixture_extraction():
    for name, (n_records, n_components, n_unresolved, n_power_ports, n_net_labels) in EXPECTED.items():
        path = os.path.join(FIXTURES_DIR, name)
        records = se.read_records(path)
        parsed, comp_by_idx = _resolve_designators(records)

        assert len(records) == n_records, f"{name}: record count changed"
        assert len(comp_by_idx) == n_components, f"{name}: component count changed"

        unresolved = sum(1 for c in comp_by_idx.values() if c["designator"] == "?")
        assert unresolved == n_unresolved, f"{name}: unresolved-designator count changed"

        power_ports = {d.get("TEXT", "") for d in parsed if d.get("RECORD") == "17"}
        assert len(power_ports) == n_power_ports, f"{name}: power port count changed"

        net_labels = {d.get("TEXT", "") for d in parsed if d.get("RECORD") == "25"}
        assert len(net_labels) == n_net_labels, f"{name}: net label count changed"


def test_no_crash_on_all_fixtures():
    for path in glob.glob(os.path.join(FIXTURES_DIR, "*.SchDoc")):
        se.main(path)
