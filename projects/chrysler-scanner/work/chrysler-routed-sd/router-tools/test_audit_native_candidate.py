import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from audit_native_candidate import audit


SEED = '''(kicad_pcb (version 20260114)
 (footprint "test:R" (layer "F.Cu") (uuid "fp-1") (at 100 110 90)
  (property "Reference" "R1") (property "Value" "1k")
  (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "GND") (uuid "pad-1")))
 (segment (start 100 110) (end 101 110) (width 0.2) (locked yes)
  (layer "F.Cu") (net "GND") (uuid "locked-track")))'''


class PreservationAuditTest(unittest.TestCase):
    def run_audit(self, candidate, drc=None):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            seed_path, candidate_path = root / 'seed.kicad_pcb', root / 'candidate.kicad_pcb'
            seed_path.write_text(SEED)
            candidate_path.write_text(candidate)
            expected = root / 'expected.json'
            expected.write_text(json.dumps({'parts': {'R1': {'pins': {'1': {'net': 'GND'}}}}}))
            drc_path = None
            if drc is not None:
                drc_path = root / 'drc.json'
                drc_path.write_text(json.dumps(drc))
            before = (seed_path.read_bytes(), candidate_path.read_bytes())
            result = audit(seed_path, candidate_path, expected, drc_path)
            self.assertEqual(before, (seed_path.read_bytes(), candidate_path.read_bytes()))
            return result

    def test_additional_routing_can_preserve_every_original_item(self):
        candidate = SEED[:-1] + '''(segment (start 101 110) (end 102 110) (width 0.2)
            (layer "F.Cu") (net "GND") (uuid "new-track")))'''
        report = self.run_audit(candidate)
        self.assertTrue(report['preservation_passed'])
        self.assertEqual(report['candidate_copper']['segment'], 2)

    def test_even_fifty_nanometre_placement_drift_is_rejected(self):
        report = self.run_audit(SEED.replace('(at 100 110 90)', '(at 100.00005 110 90)'))
        self.assertFalse(report['preservation_passed'])
        self.assertEqual(report['errors'][0]['footprints_changed'], ['R1'])

    def test_pad_net_change_is_rejected_both_against_seed_and_expected_circuit(self):
        report = self.run_audit(SEED.replace('(net "GND") (uuid "pad-1")', '(net "WRONG") (uuid "pad-1")'))
        self.assertFalse(report['preservation_passed'])
        self.assertTrue(any('physical_pad_set_or_fields_changed' in e for e in report['errors']))
        self.assertTrue(any('expected_circuit_mismatches' in e for e in report['errors']))

    def test_lost_locked_copper_and_nonzero_native_drc_are_rejected(self):
        report = self.run_audit(SEED.replace('(uuid "locked-track")', '(uuid "replaced-track")'))
        self.assertFalse(report['locked_seed_copper_unchanged'])
        report = self.run_audit(SEED, {'violations': [], 'unconnected_items': [{'type': 'unconnected_items'}], 'schematic_parity': []})
        self.assertFalse(report['preservation_passed'])


if __name__ == '__main__':
    unittest.main()
