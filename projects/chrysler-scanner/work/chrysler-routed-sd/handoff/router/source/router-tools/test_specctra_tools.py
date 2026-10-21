import unittest

from specctra_tools import ascii_placement_metadata, atom, configure_dsn, one, parse, sanitize_ses, walk


DSN = '''(pcb "board(test)"
 (parser (string_quote ") (space_in_quoted_tokens on))
 (resolution um 10) (unit um)
 (structure
  (layer "L1 - front" (type signal) (property (index 0)))
  (layer "L2 - GND" (type power) (property (index 1)))
  (layer "L3 - Power" (type power) (property (index 2)))
  (layer "L4 - back" (type signal) (property (index 3)))
  (plane GND (polygon "L2 - GND" 0 0 0 1000 0 1000 1000))
  (via "Via[0-3]_600:300_um")
  (rule (width 250) (clearance 150) (clearance 37.5 (type smd_smd))))
 (placement (component TEST (place R1 50.05 -60.05 front 90)))
 (network
  (net GND (pins R1-1 R2-1)) (net +5V (pins J1-1 R1-2))
  (net RF_IN (pins R3-1 R4-1)) (net "D+" (pins J1-2 U1-1))
  (class kicad_default GND +5V RF_IN "D+"
    (circuit (use_via "Via[0-3]_600:300_um"))
    (rule (width 250) (clearance 150))))
 (wiring
  (wire (path "L1 - front" 400 10.05 20.05 30.05 40.05) (net RF_IN) (type protect))
  (wire (path "L1 - front" 250 100 100 200 100) (net "D+"))
  (wire (path "L4 - back" 250 0 100 100 100) (net GND) (type normal))))'''

SES = r'''(session "board(test)"
 (base_design "a\\b\"c.dsn")
 (history (self (comment "placement (must stay)")))
 (placement (resolution um 10)
   (component "R(1)" (place "R(1)" 100.05 200.05 back 180)))
 (routes (resolution um 10)
  (parser (string_quote ") (space_in_quoted_tokens on))
  (library_out (padstack "Via[0-3]_600:300_um" (shape (circle pcb 600))))
  (network_out (net "N(foo)" (wire (path "L1 (front)" 200 1 2 3 4))))))'''


class SpecctraTransformsTest(unittest.TestCase):
    def test_ses_removes_only_top_level_placement_and_keeps_routes_exact(self):
        before = one(parse(SES), 'routes')
        result, report = sanitize_ses(SES)
        after = one(parse(result), 'routes')
        self.assertEqual(result[after.start:after.end], SES[before.start:before.end])
        self.assertFalse(parse(result).children('placement'))
        self.assertIn('placement (must stay)', result)
        self.assertEqual(report, {'placement_scopes_removed': 1, 'routes_bytes_unchanged': True})

    def test_ses_without_placement_is_unchanged_and_idempotent(self):
        result, _ = sanitize_ses(SES)
        again, report = sanitize_ses(result)
        self.assertEqual(again, result)
        self.assertEqual(report['placement_scopes_removed'], 0)

    def test_ses_duplicate_placement_is_rejected(self):
        malformed = SES.replace('(routes', '(placement) (routes', 1)
        with self.assertRaisesRegex(ValueError, 'Multiple'):
            sanitize_ses(malformed)

    def test_ses_requires_routes_and_correct_root(self):
        for text in ['(session test)', DSN, '(session test (placement)) trailing']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                sanitize_ses(text)

    def test_quotes_parentheses_escapes_and_comments_do_not_break_balance(self):
        parsed = parse(r'''(session "a(b)\"c" ; ignored ( unmatched
          (routes (comment "doubled ""quote"" (fine)")))''')
        self.assertEqual(atom(parsed), 'a(b)"c')
        self.assertEqual(atom(one(one(parsed, 'routes'), 'comment')), 'doubled "quote" (fine)')

    def test_unclosed_or_extra_root_is_rejected(self):
        for text in ['(session (routes)', '(session "unfinished)', '(session x)(session y)', '(pcb (parser (string_quote \')))']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)

    def test_configure_disjoint_classes_clearances_and_fixed_existing_copper(self):
        result, report = configure_dsn(DSN, rails=['+5V'], critical_rf=['RF_IN'],
                                       critical_usb=['D+'], rf_width_um=400)
        root = parse(result)
        classes = {atom(c): c for c in one(root, 'network').children('class')}
        self.assertEqual(set(classes), {'kicad_default', 'rails', 'rf_fixed', 'usb_fixed'})
        for name, width in [('kicad_default', '200'), ('rails', '500'), ('rf_fixed', '400'), ('usb_fixed', '250')]:
            self.assertEqual(atom(one(one(classes[name], 'rule'), 'width')), width)
        self.assertEqual(atom(one(one(classes['rf_fixed'], 'circuit'), 'use_layer')), 'L1 - front')
        for clearance in [s for s in walk(root) if s.head == 'clearance']:
            self.assertGreaterEqual(float(atom(clearance)), 150)
        wires = one(root, 'wiring').children('wire')
        self.assertEqual([atom(one(w, 'type')) for w in wires], ['fix', 'fix', 'normal'])
        self.assertEqual(report['existing_critical_copper_scopes_fixed'], 2)
        # Copper paths, native placement coordinates and planes are preserved.
        for before, after in zip(one(parse(DSN), 'wiring').children('wire'), wires):
            a, b = one(before, 'path'), one(after, 'path')
            self.assertEqual(DSN[a.start:a.end], result[b.start:b.end])
        for name in ['placement']:
            a, b = one(parse(DSN), name), one(root, name)
            self.assertEqual(DSN[a.start:a.end], result[b.start:b.end])

    def test_unknown_or_overlapping_nets_are_rejected(self):
        for kwargs in [dict(rails=['MISSING']), dict(rails=['+5V'], critical_usb=['+5V']), dict(critical_rf=['RF_IN'])]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                configure_dsn(DSN, **kwargs)

    def test_unsafe_rules_or_units_are_rejected(self):
        for kwargs in [dict(clearance_um=100), dict(default_width_um=100), dict(rail_width_um=float('nan'))]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                configure_dsn(DSN, **kwargs)
        with self.assertRaises(ValueError):
            configure_dsn(DSN.replace('(unit um)', '(unit mil)'))

    def test_existing_custom_classes_are_not_silently_destroyed(self):
        with self.assertRaisesRegex(ValueError, 'custom'):
            configure_dsn(DSN.replace('class kicad_default', 'class already_reviewed'))

    def test_ascii_normalization_changes_only_optional_pn_annotations(self):
        original = DSN.replace('(place R1 50.05 -60.05 front 90)',
            '(place R1 50.05 -60.05 front 90 (PN "4.7kΩ")) (place C1 100 100 front 0 (PN 10μF))')
        result, report = ascii_placement_metadata(original)
        self.assertIn('(PN "4.7kohm")', result)
        self.assertIn('(PN "10uF")', result)
        self.assertEqual(report['pn_annotations_normalized'], 2)
        for scope_name in ['structure', 'network', 'wiring']:
            a, b = one(parse(original), scope_name), one(parse(result), scope_name)
            self.assertEqual(original[a.start:a.end], result[b.start:b.end])
        self.assertIn('50.05 -60.05 front 90', result)
        self.assertEqual(ascii_placement_metadata(result)[0], result)

    def test_non_ascii_electrical_identifier_or_unknown_value_fails_closed(self):
        for original in [DSN.replace('RF_IN', 'RF_Ω'), DSN.replace('(place R1 50.05 -60.05 front 90)',
                '(place R1 50.05 -60.05 front 90 (PN "bad♥"))')]:
            with self.subTest(original=original), self.assertRaises(ValueError):
                ascii_placement_metadata(original)


if __name__ == '__main__':
    unittest.main()
