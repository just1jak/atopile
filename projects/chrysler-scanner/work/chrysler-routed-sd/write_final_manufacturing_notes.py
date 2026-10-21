"""Record the checked board's actual saved via processing requirements."""
from pathlib import Path
import hashlib
import json
import pcbnew as p

ROOT = Path(__file__).resolve().parent
DESIGN = ROOT / 'design'
BOARD = DESIGN / 'ChryslerScanner_V240_SD.kicad_pcb'


def main():
    drc = json.loads((DESIGN / 'reference/final-drc.json').read_text())
    assert not any(drc[k] for k in ('violations', 'unconnected_items', 'schematic_parity'))
    assert drc['source'] == BOARD.name
    original = BOARD.read_bytes()
    stamp = BOARD.stat().st_mtime_ns
    b = p.LoadBoard(str(BOARD))
    pads = [(f, q) for f in b.GetFootprints() for q in f.Pads()
            if q.GetAttribute() == p.PAD_ATTRIB_SMD]
    sites, missing = [], []
    for via in b.GetTracks():
        if via.GetClass() != 'PCB_VIA':
            continue
        overlapping = set()
        for fp, pad in pads:
            for copper, mask in ((p.F_Cu, p.F_Mask), (p.B_Cu, p.B_Mask)):
                if (pad.IsOnLayer(copper) and pad.IsOnLayer(mask)
                        and via.GetEffectiveHoleShape().Collide(pad.GetEffectiveShape(copper),
                            max(0, pad.GetSolderMaskExpansion(copper)))):
                    overlapping.add(fp.GetReference() + '.' + pad.GetNumber())
        filled = via.GetPrimaryDrillFilledFlag()
        capped = via.GetPrimaryDrillCappedFlag()
        if overlapping and not (filled and capped):
            missing.append(via.m_Uuid.AsString())
        if not (filled or capped):
            continue
        assert filled is True and capped is True, 'Partially specified VIPPO process'
        pos = via.GetPosition()
        sites.append(dict(uuid=via.m_Uuid.AsString(), net=via.GetNetname(),
            positionMm=[p.ToMM(pos.x), p.ToMM(pos.y)],
            diameterMm=p.ToMM(via.GetWidth(p.F_Cu)), drillMm=p.ToMM(via.GetDrillValue()),
            filled=filled, copperCapped=capped, overlappingSmdPadApertures=sorted(overlapping),
            frontTented=via.GetFrontTentingMode() == p.TENTING_MODE_TENTED,
            backTented=via.GetBackTentingMode() == p.TENTING_MODE_TENTED))
    assert not missing, ('Unfilled drill overlaps a surface-mount pad mask aperture', missing)
    assert BOARD.read_bytes() == original and BOARD.stat().st_mtime_ns == stamp
    sites.sort(key=lambda v: (v['positionMm'], v['net']))
    report = dict(pcbSha256=hashlib.sha256(original).hexdigest(),
        process='Nonconductive resin filled, copper capped and planarized through vias (VIPPO)',
        sites=sites, missingFilledCappedFlagsForSmdApertureOverlap=missing,
        originalBoardUnchanged=True, nativeReloadFlagsVerified=True,
        boardSizeMm=[110, 55], copperLayers=4,
        firmwareStatus='deferred_by_user', manufacturingOrderPlaced=False)
    ref = DESIGN / 'reference'
    (ref / 'via-fabrication-requirements.json').write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# Manufacturing and assembly requirements', '',
        'These requirements describe the exact checked PCB identified below. They do not constitute a manufacturing order or hardware qualification.', '',
        '**PCB SHA256:** `' + report['pcbSha256'] + '`', '',
        'The board is 110 × 55 mm with four copper layers and nominal 1.6 mm thickness. Preserve the inner ground reference, antenna keepouts and native geometry. RF/USB impedance targets require review against the actual fabricator stackup.', '',
        '## Filled and capped vias', '',
        'Every site in this table requires nonconductive resin fill, copper capping and planarization (VIPPO). Ordinary open or tented drilled vias cannot replace this process. Tenting settings do not replace filling/capping. The actual saved KiCad filling and capping flags were reloaded and checked. All surface-mount pad apertures intersected by drills have these flags.', '',
        '| Net / nearby pads | X mm | Y mm | Copper / drill mm | Front / rear tenting | UUID |',
        '| --- | ---: | ---: | --- | --- | --- |']
    for v in sites:
        target = v['net'] + ' / ' + (', '.join(v['overlappingSmdPadApertures']) or 'pad-edge escape')
        tenting = ('tented' if v['frontTented'] else 'open') + ' / ' + ('tented' if v['backTented'] else 'open')
        lines.append('| %s | %.6f | %.6f | %.2f / %.2f | %s | %s |' %
            (target, *v['positionMm'], v['diameterMm'], v['drillMm'], tenting, v['uuid']))
    lines += ['', '## Assembly and prototype checks', '',
        'Outer ground fills connect surface-mount ground pads solidly; through-hole pads use thermal reliefs. Account for ground copper and exposed-pad vias in the stencil and reflow process.', '',
        'The microSD socket and its regulator/capacitors are on the underside. Provide card access and at least 7 mm underside clearance; verify enclosure fit against the actual parts.', '',
        'Prototype checks still include supply droop and peak SD current, shared +5 V capacity, regulator temperature, RF/USB signal integrity and vehicle-interface behavior. The design has no RTC or shutdown hold-up. Firmware remains deferred and the current firmware has not been made to log to this SD socket.', '']
    (ref / 'MANUFACTURING-NOTES.md').write_text('\n'.join(lines))
    print(json.dumps(dict(vippoSites=len(sites), missingFlags=len(missing), pcbSha256=report['pcbSha256'])))


if __name__ == '__main__':
    main()
