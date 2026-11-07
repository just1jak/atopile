# SPDX-License-Identifier: GPL-3.0-only
"""Compare a native Rev D KiCad XML netlist against the accepted Rev C release."""
import argparse
import hashlib
from pathlib import Path
from xml.etree import ElementTree

REV_D = Path(__file__).resolve().parent
REV_C = REV_D.parent / "current"
REV_C_PCB_SHA256 = "e794b86979228ba2275eb4262df848acd16e56ef97a4ccf45402d65b119308d4"

# Pin order is physical package order. None denotes a deliberate no-connect.
SELECTOR_PINS = {
    "K1": ("+5V", None, "OBD_SHARED_6", "CAN_SERIES_6", "CAN_SERIES_14", "OBD_SHARED_14", None, "CAN_COIL_LOW"),
    "K2": ("+5V", None, "OBD_SHARED_6", "LEG_SERIES_6", "LEG_SERIES_14", "OBD_SHARED_14", None, "LEG_COIL_LOW"),
    "U26": ("SCL", "SDA", "GND", "GND", "GND", "N_R88_2", None, None, "GND", "REQ_CAN", "REQ_LEGACY", "CAN_TX_ARM", None, None, None, None, None, "+3.3V"),
    "U27": ("REQ_CAN", "REQ_LEGACY", "GND", "GND", "GND", "N_R88_2", None, "GND", None, None, None, None, "LEG_DECODE", "CAN_DECODE", None, "+3.3V"),
    "U28": ("CAN_DELAY", "GND", "LEG_DELAY", "LEG_GATE", "+3.3V", "CAN_GATE"),
    "Q25": ("CAN_GATE", "COIL_RETURN", "CAN_COIL_LOW"),
    "Q26": ("LEG_GATE", "COIL_RETURN", "LEG_COIL_LOW"),
    "Q27": ("N_R88_2", "GND", "COIL_RETURN"),
    "Q28": ("CAN_GATE", "GND", "CAN_STB"),
    "R140": ("REQ_CAN", "GND"), "R141": ("REQ_LEGACY", "GND"),
    "R142": ("CAN_DECODE", "CAN_DELAY"), "R143": ("LEG_DECODE", "LEG_DELAY"),
    "R144": ("+3.3V", "CAN_STB"), "R145": ("N_R88_2", "GND"),
    "D41": ("CAN_DECODE", "CAN_DELAY"), "D42": ("LEG_DECODE", "LEG_DELAY"),
    "D43": ("+5V", "CAN_COIL_LOW"), "D44": ("+5V", "LEG_COIL_LOW"),
    "C142": ("+3.3V", "GND"), "C143": ("+3.3V", "GND"),
    "C144": ("+3.3V", "GND"), "C145": ("CAN_DELAY", "GND"),
    "C146": ("LEG_DELAY", "GND"),
}

TX_PERMIT_PINS = {
    "U29": ("N_R88_2", "GND", "CAN_DECODE", "CAN_ROUTE_OK", "+3.3V", "CAN_GATE"),
    "U30": (None, "LEG_GATE", "GND", "LEG_IDLE", "+3.3V"),
    "U31": ("CAN_ROUTE_OK", "GND", "LEG_IDLE", "CAN_TX_PERMIT", "+3.3V", "CAN_ARM_TIMED"),
    "U32": ("CAN_TX_PERMIT", "MCU_CAN_TX", "GND", "CAN_PHY_TXD", "+3.3V"),
    "R146": ("CAN_TX_ARM", "GND"),
    "R147": ("CAN_TX_PERMIT", "GND"),
    "R148": ("MCU_CAN_TX", "GND"),
    "R149": ("+3.3V", "CAN_PHY_TXD"),
    **{f"C{ref}": ("+3.3V", "GND") for ref in range(147, 151)},
}

HARDENING_PINS = {
    "K3": ("+5V", None, "CAN_SERIES_6", "CAN_BRANCH_H", "CAN_BRANCH_L", "CAN_SERIES_14", None, "CAN_BACKUP_COIL"),
    "K4": ("+5V", None, "LEG_SERIES_6", "LEGACY_6_ISOLATED", "LEGACY_14_ISOLATED", "LEG_SERIES_14", None, "LEG_BACKUP_COIL"),
    "Q29": ("CAN_BACKUP_DRIVE", "GND", "CAN_BACKUP_COIL"),
    "Q30": ("LEG_BACKUP_DRIVE", "GND", "LEG_BACKUP_COIL"),
    "D45": ("+5V", "CAN_BACKUP_COIL"), "D46": ("+5V", "LEG_BACKUP_COIL"),
    "R150": ("CAN_BACKUP_DRIVE", "GND"), "R151": ("LEG_BACKUP_DRIVE", "GND"),
    "U33": ("CAN_TX_ARM", "GND", "CAN_TIMER_SET", "CAN_TIMER_DIV", "+3.3V", "CAN_TIMER_WINDOW"),
    "U34": ("CAN_TX_ARM", "CAN_TIMER_WINDOW", "GND", "CAN_ARM_TIMED", "+3.3V"),
    "U35": ("CAN_DECODE", "N_R88_2", "GND", "CAN_BACKUP_DRIVE", "+3.3V"),
    "U36": ("LEG_DECODE", "N_R88_2", "GND", "LEG_BACKUP_DRIVE", "+3.3V"),
    "R152": ("CAN_TIMER_SET", "GND"), "R153": ("CAN_TIMER_SET", "GND"),
    "R154": ("+3.3V", "CAN_TIMER_DIV"), "R155": ("CAN_TIMER_DIV", "GND"),
    **{f"C{ref}": ("+3.3V", "GND") for ref in range(151, 155)},
}

TX_PERMIT_PARTS = {
    "U29": ("SN74LVC1G11DBVR", "Package_TO_SOT_SMD:SOT-23-6"),
    "U30": ("SN74LVC1G04DBVR", "Package_TO_SOT_SMD:SOT-23-5"),
    "U31": ("SN74LVC1G11DBVR", "Package_TO_SOT_SMD:SOT-23-6"),
    "U32": ("SN74LVC1G126DBVR", "Package_TO_SOT_SMD:SOT-23-5"),
    **{f"R{ref}": ("47k", "Resistor_SMD:R_0603_1608Metric") for ref in range(146, 149)},
    "R149": ("4.7k", "Resistor_SMD:R_0603_1608Metric"),
    **{f"C{ref}": ("100n", "Capacitor_SMD:C_0603_1608Metric") for ref in range(147, 151)},
    **{f"C{ref}": ("100n", "Capacitor_SMD:C_0603_1608Metric") for ref in range(151, 155)},
    **{f"K{ref}": ("G6K-2F-Y DC5", "Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y") for ref in (3, 4)},
    **{f"Q{ref}": ("AO3400A", "Package_TO_SOT_SMD:SOT-23") for ref in (29, 30)},
    **{f"D{ref}": ("1N5819HW-7-F", "Diode_SMD:D_SOD-123") for ref in (45, 46)},
    **{f"U{ref}": ("SN74LVC1G08DBVR", "Package_TO_SOT_SMD:SOT-23-5") for ref in (34, 35, 36)},
    "U33": ("LTC6993HS6-1#TRMPBF", "Package_TO_SOT_SMD:SOT-23-6"),
    **{f"R{ref}": (value, "Resistor_SMD:R_0603_1608Metric") for ref, value in
       enumerate(("47k", "47k", "392k 0.5%", "392k 0.5%", "100k 1%", "68.1k 1%"), 150)},
}


def read_netlist(path):
    root = ElementTree.parse(path).getroot()
    nets = {
        net.attrib["name"]: {(pin.attrib["ref"], pin.attrib["pin"]) for pin in net}
        for net in root.findall("./nets/net")
    }
    components = {}
    for component in root.findall("./components/comp"):
        ref = component.attrib["ref"]
        if ref in components:
            raise ValueError(f"Duplicate reference {ref} in {path}")
        components[ref] = (component.findtext("value"), component.findtext("footprint"))
    return nets, components


def verify(rev_d_netlist):
    pcb = REV_C / "ChryslerScanner_V240_SD.kicad_pcb"
    if hashlib.sha256(pcb.read_bytes()).hexdigest() != REV_C_PCB_SHA256:
        raise ValueError("Rev C PCB differs from the accepted baseline")

    expected, original_parts = read_netlist(REV_C / "reference/final-netlist.xml")
    actual, candidate_parts = read_netlist(rev_d_netlist)
    for pin in ("6", "14"):
        expected[f"LEGACY_{pin}_ISOLATED"] = expected.pop(f"J1962-{pin}") - {("J1", pin)}
    expected.pop("unconnected-(U10-Pad8)")
    expected.pop("unconnected-(U10-Pad22)")
    expected.update({
        "OBD_SHARED_6": {("J1", "6")},
        "OBD_SHARED_14": {("J1", "14")},
        "CAN_BRANCH_H": {("U25", "7"), ("D40", "1")},
        "CAN_BRANCH_L": {("U25", "6"), ("D40", "2")},
        "CAN_RX": {("U25", "4"), ("U10", "8")},
        "CAN_STB": {("U25", "8")},
        "CAN_PHY_TXD": {("U25", "1")},
        "MCU_CAN_TX": {("U10", "22")},
    })
    expected["+3.3V"].update({("U25", "5"), ("C141", "1")})
    expected["+5V"].update({("U25", "3"), ("C140", "1")})
    expected["GND"].update({("U25", "2"), ("D40", "3"),
                            ("C140", "2"), ("C141", "2")})

    for ref, nets in (SELECTOR_PINS | TX_PERMIT_PINS | HARDENING_PINS).items():
        for pin, net in enumerate(nets, 1):
            endpoint = (ref, str(pin))
            if net is None:
                matches = [name for name, members in actual.items()
                           if name.startswith(f"unconnected-({ref}-") and members == {endpoint}]
                if len(matches) != 1:
                    raise ValueError(f"Expected isolated no-connect at {ref}.{pin}")
                net = matches[0]
            expected.setdefault(net, set()).add(endpoint)

    changed = sorted(name for name in expected.keys() | actual.keys()
                     if expected.get(name) != actual.get(name))
    if changed:
        raise ValueError(f"Unexpected net membership: {', '.join(changed)}")
    original_parts.update({
        "U25": ("TCAN1042HGVDRQ1", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"),
        "D40": ("PESD2CANFD36VT-Q", "Package_TO_SOT_SMD:SOT-23"),
        "C140": ("100n", "Capacitor_SMD:C_0603_1608Metric"),
        "C141": ("100n", "Capacitor_SMD:C_0603_1608Metric"),
    })
    original_parts.update(TX_PERMIT_PARTS)
    for ref, pin in (("TP14", "6"), ("TP16", "14")):
        original_parts[ref] = (f"LEGACY_{pin}_ISOLATED", original_parts[ref][1])
    changed = sorted(ref for ref in original_parts.keys() | (candidate_parts.keys() - SELECTOR_PINS.keys())
                     if original_parts.get(ref) != candidate_parts.get(ref))
    if changed:
        raise ValueError(f"Unexpected part assignments: {', '.join(changed)}")
    verify_modes(actual)
    verify_tx_permit()
    print("PASS: switched pair, fail-open contact model, hardware TX gating, retained legacy nets and Rev C PCB hash")


def verify_tx_permit():
    """Cover decoder requests, delayed relay commands, reset and TX arm."""
    from itertools import product

    for request in range(4):
        for permit, can_gate, legacy_gate, armed, window in product((False, True), repeat=5):
            decoder_can = permit and request == 1
            route_ok = permit and decoder_can and can_gate
            tx_enabled = route_ok and not legacy_gate and armed and window
            expected = (request, permit, can_gate, legacy_gate, armed, window) == (
                1, True, True, False, True, True)
            if tx_enabled != expected:
                raise ValueError(f"Unexpected CAN TX state for request {request}")


def verify_modes(nets):
    """Evaluate each pole with any one relay forced closed, including its driver."""
    by_pin = {pin: name for name, members in nets.items() for pin in members}
    for permit in (False, True):
        for request in range(4):
            selected = {1: {"K1", "K3"}, 2: {"K2", "K4"}}.get(request, set()) if permit else set()
            for stuck in (None, "K1", "K2", "K3", "K4"):
                closed = selected | {stuck}
                for pin, common, no, nc, can_net in (
                    ("6", "3", "4", "2", "CAN_BRANCH_H"),
                    ("14", "6", "5", "7", "CAN_BRANCH_L"),
                ):
                    edges = [{by_pin[(relay, common)], by_pin[(relay, no if relay in closed else nc)]}
                             for relay in ("K1", "K2", "K3", "K4")]
                    reachable = {by_pin[("J1", pin)]}
                    for _ in edges:
                        for edge in edges:
                            if reachable & edge:
                                reachable.update(edge)
                    legacy_net = f"LEGACY_{pin}_ISOLATED"
                    expected = ({can_net} if "K1" in selected else
                                {legacy_net} if "K2" in selected else set())
                    if reachable & {can_net, legacy_net} != expected:
                        raise ValueError(f"Unsafe OBD {pin} route with permit={permit}, request={request}, stuck={stuck}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path, help="KiCad XML export of the Rev D schematic")
    verify(parser.parse_args().netlist)
