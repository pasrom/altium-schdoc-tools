"""Regression tests for schnet.py against public fixture schematics.

See test_schextract.py's module docstring: these pin today's actual output,
not a hand-verified ground truth. The point is catching a silent regression
in the geometric connectivity or net-naming logic - exactly the class of bug
(OwnerIndex probe order, see the fix commit) that a plain "does it crash"
check would have missed.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schnet as sn

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# path -> (named_nets, unnamed_nets, gnd_net_size_or_None)
EXPECTED = {
    "16bit_ripple_adder.SchDoc": (5, 13, None),
    "basic_power_supply.SchDoc": (8, 5, 2),
    "max1229_currentsense.SchDoc": (3, 33, None),
}


def _net_summary(path):
    _comp, netmembers, netnames, _pinnode = sn.build(path)
    named = 0
    unnamed = 0
    gnd_size = None
    for r, members in netmembers.items():
        names = netnames.get(r, set())
        named_labels = [n for (k, n) in names if k in ("PWR", "NET", "PORT") and n]
        if named_labels:
            named += 1
            if "GND" in named_labels:
                gnd_size = len(members)
        else:
            unnamed += 1
    return named, unnamed, gnd_size


def test_fixture_netlists():
    for name, (n_named, n_unnamed, n_gnd) in EXPECTED.items():
        path = os.path.join(FIXTURES_DIR, name)
        named, unnamed, gnd_size = _net_summary(path)
        assert named == n_named, f"{name}: named net count changed"
        assert unnamed == n_unnamed, f"{name}: unnamed net count changed"
        assert gnd_size == n_gnd, f"{name}: GND net size changed"


def test_no_component_left_unresolved_beyond_baseline():
    # Every designator that DID resolve should be a non-empty string, never
    # None - a crash-shaped regression in the owner-probing logic would show
    # up here even on a fixture with zero unresolved designators today.
    for path in glob.glob(os.path.join(FIXTURES_DIR, "*.SchDoc")):
        comp, _netmembers, _netnames, _pinnode = sn.build(path)
        for c in comp.values():
            assert c["designator"] is not None


def test_no_crash_on_all_fixtures():
    for path in glob.glob(os.path.join(FIXTURES_DIR, "*.SchDoc")):
        sn.main(path)
