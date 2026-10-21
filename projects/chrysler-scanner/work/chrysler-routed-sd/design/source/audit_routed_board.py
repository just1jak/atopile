"""Read-only native audit of a routed copy against the frozen route seed.

Run with KiCad's bundled Python. Zone fill is recomputed only in memory.
No board, project, routing seed, or source file is saved by this helper.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
import pcbnew as p


def uid(item):
    return item.m_Uuid.AsString()


def xy(point):
    return [point.x, point.y]


def blocks(raw, kind):
    chunks = re.findall(r'(?ms)^\t\(' + kind + r'\b.*?^\t\)\n', raw.decode())
    result = {}
    for index, chunk in enumerate(chunks):
        match = re.search(r'(?m)^\t\t\(uuid "([^"]+)"\)', chunk)
        result[match.group(1) if match else str(index)] = chunk
    return result


def native_footprints(board):
    result = {}
    for fp in board.GetFootprints():
        result[uid(fp)] = dict(reference=fp.GetReference(), value=fp.GetValue(),
            position=xy(fp.GetPosition()), orientation=fp.GetOrientationDegrees(),
            layer=fp.GetLayer(), locked=fp.IsLocked(),
            pads={uid(q): dict(number=q.GetNumber(), net=q.GetNetname(),
                position=xy(q.GetPosition()), size=xy(q.GetSize()),
                orientation=q.GetOrientationDegrees(), shape=int(q.GetShape()),
                drill=xy(q.GetDrillSize()), offset=xy(q.GetOffset()),
                attribute=int(q.GetAttribute()), layers=list(q.GetLayerSet().Seq()))
                for q in fp.Pads()})
    return result


def copper(item):
    width = item.GetWidth(p.F_Cu) if item.GetClass() == 'PCB_VIA' else item.GetWidth()
    result = dict(kind=item.GetClass(), net=item.GetNetname(),
        start=xy(item.GetStart()), end=xy(item.GetEnd()),
        width=width, layer=item.GetLayer(), locked=item.IsLocked())
    if item.GetClass() == 'PCB_VIA':
        result.update(drill=item.GetDrillValue(), via_type=int(item.GetViaType()),
            top=item.TopLayer(), bottom=item.BottomLayer(),
            front_tenting=int(item.GetFrontTentingMode()),
            back_tenting=int(item.GetBackTentingMode()))
    if item.GetClass() == 'PCB_ARC':
        result['mid'] = xy(item.GetMid())
    return result


def chain(outline):
    assert outline.ArcCount() == 0, 'Unexpected zone boundary arc; audit explicitly before release'
    return [xy(outline.CPoint(i)) for i in range(outline.PointCount())]


def zone_signature(zone):
    outline = zone.Outline()
    getters = ('GetAssignedPriority', 'GetFillMode', 'GetLocalClearance',
        'GetMinThickness', 'GetPadConnection', 'GetThermalReliefGap',
        'GetThermalReliefSpokeWidth', 'GetIslandRemovalMode', 'GetMinIslandArea',
        'GetCornerRadius', 'GetCornerSmoothingType', 'GetHatchThickness',
        'GetHatchGap', 'GetHatchOrientation', 'GetHatchSmoothingLevel',
        'GetHatchSmoothingValue', 'GetHatchHoleMinArea')
    settings = {}
    for name in getters:
        value = getattr(zone, name)()
        if hasattr(value, 'AsDegrees'):
            value = value.AsDegrees()
        assert isinstance(value, (int, float, bool, str)), (name, type(value))
        settings[name] = value
    return dict(net=zone.GetNetname(), name=zone.GetZoneName(),
        layers=list(zone.GetLayerSet().Seq()), rule_area=zone.GetIsRuleArea(),
        disallow_tracks=zone.GetDoNotAllowTracks(), disallow_vias=zone.GetDoNotAllowVias(),
        disallow_pads=zone.GetDoNotAllowPads(), disallow_fills=zone.GetDoNotAllowZoneFills(),
        disallow_footprints=zone.GetDoNotAllowFootprints(), settings=settings,
        outlines=[dict(points=chain(outline.COutline(i)),
            holes=[chain(outline.CHole(i,j)) for j in range(outline.HoleCount(i))])
            for i in range(outline.OutlineCount())])


def changed_keys(before, after):
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def connectivity(board):
    p.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    c = board.GetConnectivity()
    pads = {uid(q): q for fp in board.GetFootprints() for q in fp.Pads()}
    labels = {uid(q): fp.GetReference()+'.'+q.GetNumber()
              for fp in board.GetFootprints() for q in fp.Pads()}
    by_net = collections.defaultdict(set)
    for key, pad in pads.items():
        if pad.GetNetname():
            by_net[pad.GetNetname()].add(key)
    disconnected = {}
    ground = None
    for net, expected in by_net.items():
        pending = set(expected)
        groups = []
        while pending:
            anchor = next(iter(pending))
            members = {uid(item) for item in c.GetConnectedItems(pads[anchor]) if uid(item) in pads}
            members.add(anchor)
            members &= expected
            groups.append(members)
            pending -= members
        groups.sort(key=lambda group: (-len(group), sorted(group)))
        if len(groups) > 1:
            disconnected[net] = [dict(count=len(g), pads=sorted(labels[k] for k in g)) for g in groups]
        if net == 'GND':
            ground = dict(padCount=len(expected), connectedGroupCount=len(groups),
                largestConnectedGroupCount=len(groups[0]),
                isolatedFromMainGroup=sorted(labels[k] for g in groups[1:] for k in g))
    return dict(fullNativeAirwires=c.GetUnconnectedCount(False),
        disconnectedNetGroups=disconnected, ground=ground,
        planeFilledAreasMm2={uid(z): round(z.CalculateFilledArea()/1e12, 6)
            for z in board.Zones() if not z.GetIsRuleArea()})


RAILS = ('J1962-16', '+12V', '+3.3V', '+5V', '+7.5V', 'VBUS', 'N_C3_1',
         'VBB', 'VPP', 'SD_3V3', 'N_R2_1', 'N_R8_1', 'N_R11_1', 'N_R14_1')


def audit(seed_path, final_path, require_complete=False, drc_path=None, zone_baseline_path=None):
    seed_project = seed_path.with_suffix('.kicad_pro')
    final_project = final_path.with_suffix('.kicad_pro')
    paths = {seed_path, final_path, seed_project, final_project}
    if zone_baseline_path:
        paths.add(zone_baseline_path)
    originals = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                 for path in paths
                 if path.exists()}
    seed_raw, final_raw = originals[seed_path][0], originals[final_path][0]
    seed, board = p.LoadBoard(str(seed_path)), p.LoadBoard(str(final_path))
    changes = {}
    changes['footprintBlocks'] = changed_keys(blocks(seed_raw, 'footprint'), blocks(final_raw, 'footprint'))
    changes['nativeFootprintsAndPads'] = changed_keys(native_footprints(seed), native_footprints(board))
    seed_copper = {uid(t): copper(t) for t in seed.GetTracks()}
    final_copper = {uid(t): copper(t) for t in board.GetTracks()}
    changes['protectedCopper'] = sorted(key for key, value in seed_copper.items()
                                        if final_copper.get(key) != value)
    for kind in ('segment', 'arc', 'via'):
        before_blocks, after_blocks = blocks(seed_raw, kind), blocks(final_raw, kind)
        changed = sorted(key for key,value in before_blocks.items() if after_blocks.get(key) != value)
        if changed:
            changes['protected'+kind.title()+'Blocks'] = changed
    seed_zones = {uid(z): zone_signature(z) for z in seed.Zones()}
    final_zones = {uid(z): zone_signature(z) for z in board.Zones()}
    expected_zones = seed_zones
    zone_board = None
    if zone_baseline_path:
        zone_board = p.LoadBoard(str(zone_baseline_path))
        expected_zones = {uid(z): zone_signature(z) for z in zone_board.Zones()}
        assert all(expected_zones.get(key) == value for key,value in seed_zones.items()), \
            'Approved zone baseline changes an original seed plane or keepout'
    changes['zonesAndAntennaKeepouts'] = changed_keys(expected_zones, final_zones)
    approved_status_text = []
    for kind in ('layers', 'setup', 'gr_line', 'gr_arc', 'gr_rect', 'gr_poly', 'gr_text'):
        before_drawing = blocks(seed_raw, kind)
        after_drawing = blocks(final_raw, kind)
        differences = changed_keys(before_drawing, after_drawing)
        if kind == 'gr_text':
            # One exact drawing-only status replacement is permitted after
            # complete routing; position, UUID, layer and typography stay exact.
            old_status = 'SD LOGGER - NEW CIRCUIT UNROUTED / FIRMWARE DEFERRED'
            new_status = 'SD LOGGER - ROUTED / FIRMWARE DEFERRED'
            for key in list(differences):
                old = before_drawing.get(key, '')
                if (old.count(old_status) == 1 and '(layer "Dwgs.User")' in old
                        and old.replace(old_status, new_status) == after_drawing.get(key)):
                    approved_status_text.append(key)
                    differences.remove(key)
        if differences:
            changes[kind] = differences
    project_settings_equal = False
    if seed_project.exists() and final_project.exists():
        before_project = json.loads(originals[seed_project][0])
        after_project = json.loads(originals[final_project][0])
        project_settings_equal = (before_project['board']['design_settings'] ==
                                  after_project['board']['design_settings'])
        if not project_settings_equal:
            changes['nativeProjectDesignSettings'] = ['changed']
    non_copper, thin, gnd_plane_tracks = [], [], []
    layer_counts = collections.Counter()
    rails = {net: collections.defaultdict(float) for net in RAILS}
    for track in board.GetTracks():
        if track.GetClass() == 'PCB_VIA':
            continue
        if track.GetLayer() not in (p.F_Cu, p.B_Cu, p.In1_Cu, p.In2_Cu):
            non_copper.append(uid(track))
        layer = p.LayerName(track.GetLayer())
        layer_counts[layer] += 1
        if track.GetWidth() < p.FromMM(.15):
            thin.append(dict(uuid=uid(track), net=track.GetNetname(), widthMm=p.ToMM(track.GetWidth())))
        if track.GetLayer() == p.In1_Cu and track.GetNetname() != 'GND':
            gnd_plane_tracks.append(dict(uuid=uid(track), net=track.GetNetname()))
        if track.GetNetname() in rails:
            rails[track.GetNetname()][round(p.ToMM(track.GetWidth()),6)] += p.ToMM(track.GetLength())
    connection = connectivity(board)
    report = dict(seed=str(seed_path), candidate=str(final_path),
        auditMode='complete acceptance' if require_complete else 'preservation only',
        seedSha256=hashlib.sha256(seed_raw).hexdigest(),
        candidateSha256=hashlib.sha256(final_raw).hexdigest(),
        changes=changes, approvedDrawingOnlyStatusTextChanges=approved_status_text,
        footprintCount=len(native_footprints(board)),
        protectedSeedCopperCount=len(seed_copper),
        protectedSeedLockedCopperCount=sum(v['locked'] for v in seed_copper.values()),
        trackSegmentsByCanonicalLayer=dict(layer_counts), routesOnNonCopper=non_copper,
        tracksBelow0p15mm=thin, nonGroundTracksOnGroundReferenceLayer=gnd_plane_tracks,
        railLengthByWidthMm={net: {str(width):round(length,5) for width,length in sorted(widths.items())}
                            for net,widths in rails.items()},
        zoneBoundaryAndSettingsPreservation=not changes['zonesAndAntennaKeepouts'],
        nativeProjectDesignSettingsAndExclusionsUnchanged=project_settings_equal,
        nativeZoneRefillInMemory=True, **connection)
    if zone_baseline_path:
        report['approvedZoneBaseline'] = dict(path=str(zone_baseline_path),
            sha256=hashlib.sha256(originals[zone_baseline_path][0]).hexdigest(),
            addedZoneUuids=sorted(set(expected_zones)-set(seed_zones)))
    if drc_path:
        drc = json.loads(drc_path.read_text())
        report['nativeDrc'] = dict(path=str(drc_path), errors=sum(v['severity']=='error' for v in drc['violations']),
            warnings=sum(v['severity']=='warning' for v in drc['violations']),
            reportedUnconnectedListCount=len(drc.get('unconnected_items', [])),
            sourceMatchesCandidate=drc.get('source') == final_path.name,
            bothErrorAndWarningChecksIncluded={'error','warning'} <= set(drc.get('included_severities',[])))
    files_unchanged = all(path.read_bytes() == raw and path.stat().st_mtime_ns == mtime
                          for path,(raw,mtime) in originals.items())
    report['inputFilesBytesAndMtimeUnchanged'] = files_unchanged
    report['preservationAndMinimumGeometryPassed'] = (not any(changes.values()) and not thin
        and not non_copper and files_unchanged)
    report['completeConnectivityPassed'] = (connection['fullNativeAirwires'] == 0
        and not connection['disconnectedNetGroups'] and connection['ground'] is not None
        and connection['ground']['connectedGroupCount'] == 1)
    if approved_status_text and not report['completeConnectivityPassed']:
        report['preservationAndMinimumGeometryPassed'] = False
    report['groundReferenceLayerUnbrokenBySignalTracks'] = not gnd_plane_tracks
    report['auditPassed'] = report['preservationAndMinimumGeometryPassed']
    if require_complete:
        report['auditPassed'] &= report['completeConnectivityPassed']
        report['auditPassed'] &= report['groundReferenceLayerUnbrokenBySignalTracks']
        report['auditPassed'] &= project_settings_equal
        report['auditPassed'] &= bool(drc_path) and not any(report['nativeDrc'][n] for n in ('errors', 'warnings'))
        if drc_path:
            report['auditPassed'] &= report['nativeDrc']['sourceMatchesCandidate']
            report['auditPassed'] &= report['nativeDrc']['bothErrorAndWarningChecksIncluded']
    return report


def self_test(seed_path):
    first, second = p.LoadBoard(str(seed_path)), p.LoadBoard(str(seed_path))
    assert native_footprints(first) == native_footprints(second)
    fp = next(iter(second.GetFootprints()))
    old = fp.GetPosition()
    fp.SetPosition(p.VECTOR2I(old.x+p.FromMM(.01), old.y))
    assert changed_keys(native_footprints(first), native_footprints(second)) == [uid(fp)]
    second = p.LoadBoard(str(seed_path))
    pad = next(iter(next(iter(second.GetFootprints())).Pads()))
    old = pad.GetPosition()
    pad.SetPosition(p.VECTOR2I(old.x, old.y+p.FromMM(.01)))
    assert changed_keys(native_footprints(first), native_footprints(second))
    tracks = {uid(t): copper(t) for t in first.GetTracks()}
    track = next(t for t in second.GetTracks() if t.GetClass() != 'PCB_VIA')
    track.SetWidth(track.GetWidth()+p.FromMM(.01))
    assert tracks[uid(track)] != copper(track)
    zone = next(iter(second.Zones()))
    before = zone_signature(zone)
    zone.SetDoNotAllowTracks(not zone.GetDoNotAllowTracks())
    assert zone_signature(zone) != before
    return {'footprintMoveDetected': True, 'padMoveDetected': True,
            'protectedCopperWidthChangeDetected': True, 'keepoutRuleChangeDetected': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seed', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--drc', type=Path)
    parser.add_argument('--zone-baseline', type=Path,
        help='Explicit approved board containing original zones plus reviewed additional zones')
    parser.add_argument('--run-drc', action='store_true', help='Run fresh full native DRC into output directory')
    parser.add_argument('--require-complete', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.run_drc:
        args.drc = args.output.parent/'fresh-native-drc.json'
        command = ['/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli', 'pcb', 'drc',
            '--format', 'json', '--all-track-errors', '--refill-zones',
            '--output', str(args.drc.resolve()), str(args.candidate.resolve())]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (args.output.parent/'fresh-native-drc.log').write_text(result.stdout+result.stderr)
        if result.returncode != 0:
            raise RuntimeError('Native DRC failed: '+result.stdout[-1000:]+result.stderr[-1000:])
    report = audit(args.seed.resolve(), args.candidate.resolve(), args.require_complete, args.drc,
        args.zone_baseline.resolve() if args.zone_baseline else None)
    report['freshNativeDrcRunByThisInvocation'] = args.run_drc
    if args.self_test:
        report['selfTests'] = self_test(args.seed.resolve())
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in
        ('disconnectedNetGroups', 'railLengthByWidthMm', 'ground')}, indent=2))
    return 0 if report['auditPassed'] else 1


if __name__ == '__main__':
    sys.exit(main())
