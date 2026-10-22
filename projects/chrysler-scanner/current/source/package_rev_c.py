"""Gate and export a local Rev C prototype package; never promotes or uploads.

Run with KiCad Python only after the routing owner declares the candidate clean.
Output directories must not exist. All source CAD bytes are checked unchanged.
"""
from pathlib import Path
import argparse, csv, hashlib, json, re, shutil, subprocess, sys, zipfile
import xml.etree.ElementTree as ET
import pcbnew as p

HERE = Path(__file__).resolve().parent
NAME = 'ChryslerScanner_V240_SD'
sha = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()

def run(*args):
    subprocess.run([str(x) for x in args], check=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate',type=Path,default=HERE.parent if HERE.name=='source' else HERE/'candidate')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--cli',type=Path,default=Path(sys.executable).with_name('kicad-cli.exe'))
    a=ap.parse_args();d=a.candidate.resolve();out=a.output.resolve()
    archive=out.with_suffix('.zip');fabzip=out.with_name(out.name+'-fabrication').with_suffix('.zip')
    assert not out.exists() and not archive.exists() and not fabzip.exists(), 'Use a new output path'
    assert d not in out.parents and out not in d.parents, 'Output must be separate from candidate'
    pcb=d/(NAME+'.kicad_pcb');sch=d/(NAME+'.kicad_sch')
    cad=[*d.glob('*.kicad_sch'),pcb,d/(NAME+'.kicad_pro')]
    before={f:sha(f) for f in cad}
    # The portable independent audit gates fresh all-severity DRC, ERC, XML,
    # exact contracts and complete native connectivity against this PCB hash.
    run(sys.executable,d/'source/verify_safety_revision.py','--candidate',d)
    audit=json.loads((d/'reference/p1-contract-audit.json').read_text())
    assert audit['releaseGatePassed'] is True and audit['status']=='PASS'
    assert audit['pcbSha256']==sha(pcb)
    for model in re.findall(r'\(model\s+"([^\"]+)"',pcb.read_text()):
        assert model.startswith('${KIPRJMOD}/'), ('Model is not portable',model)
        asset=Path(model.replace('${KIPRJMOD}',str(d))).resolve()
        assert d in asset.parents and asset.is_file(), ('Bundled model missing',model)

    review=json.loads((d/'reference/rev-c-adversarial-review.json').read_text())
    assert review.get('layoutReviewComplete') is True and review.get('pcbSha256')==sha(pcb), 'Final adversarial PCB review missing/stale'
    assert review.get('remainingP1Findings')==[] and review.get('remainingP1SchematicFindings')==[]
    assert 'PENDING' not in review['status'].upper() and ('ACCEPT' in review['status'].upper() or review['status']=='PASS')
    assert review['schematicSha256']=={f.name:sha(f) for f in d.glob('*.kicad_sch')}
    for key,name in [('finalNetlistSha256','final-netlist.xml'),('finalErcSha256','final-erc.json'),
                     ('safetyContractSha256','rev-c-safety-contract.md'),('manifestSha256','p1-remediation-manifest.json')]:
        assert review[key]==sha(d/'reference'/name), ('Adversarial evidence stale',name)
    bounds=json.loads((d/'reference/safety-bounds-audit.json').read_text())
    assert bounds['status']=='PASS' and all(bounds['checks'].values())
    assert bounds['contractSha256']==sha(d/'reference/rev-c-safety-contract.md')
    assert all(sha(f)==digest for f,digest in before.items())
    ordinary_ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*-backups','__pycache__','_autosave*','.git','SHA256SUMS.txt','*.sha256')
    def ignore(folder,names):
        excluded=set(ordinary_ignore(folder,names))
        if Path(folder).resolve()==d:
            excluded.update(n for n in names if n in ('fabrication','previews','BOM.csv') or n.lower().endswith('.pdf'))
        return excluded
    shutil.copytree(d,out,symlinks=False,ignore=ignore)
    # Old final-* reports are evidence of older boards, never current evidence.
    ref=out/'reference';history=ref/'historical-pre-rev-c';history.mkdir(exist_ok=True)
    keep={'MANUFACTURING-NOTES.md','final-drc.json','final-erc.json','final-netlist.xml','p1-contract-audit.json',
          'p1-remediation-manifest.json','rev-c-safety-contract.md','pre-p1',
          'rev-c-adversarial-review.md','rev-c-adversarial-review.json',
          'original-schematic-comparison.md'}
    for f in list(ref.iterdir()):
        current_evidence=f.name.startswith(('rev-c-','p1-','safety-')) or 'exception' in f.name
        if f.name not in keep and not current_evidence and f!=history and f.is_file():
            target=history/f.name
            assert not target.exists(), ('Historical filename collision; resolve explicitly',target)
            shutil.move(str(f),str(target))
    (history/'README.md').write_text('Historical evidence only. These files do not certify Rev C. Use ../p1-contract-audit.json and ../final-drc.json / final-erc.json for this package.\n')
    copied=out/pcb.name;fab=out/'fabrication';fab.mkdir()
    run(a.cli,'pcb','export','gerbers','--layers','F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts','--output',str(fab)+'/',copied)
    run(a.cli,'pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--generate-map','--map-format','pdf','--generate-report','--output',str(fab)+'/',copied)
    run(a.cli,'pcb','export','pos','--format','csv','--units','mm','--side','both','--exclude-dnp','--output',fab/'assembly-positions.csv',copied)
    run(a.cli,'sch','export','pdf','--output',out/(NAME+'-Hierarchy.pdf'),out/sch.name)
    previews=out/'previews';previews.mkdir()
    run(a.cli,'pcb','export','pdf','--mode-single','--scale','0','--layers','F.Cu,F.Fab,F.Silkscreen,Edge.Cuts','--output',previews/'front-routing.pdf',copied)
    run(a.cli,'pcb','export','pdf','--mode-single','--scale','0','--mirror','--layers','B.Cu,B.Fab,B.Silkscreen,Edge.Cuts','--output',previews/'back-routing.pdf',copied)
    assert len(list(fab.glob('*.gbrjob')))==1, 'Native Gerber job missing; do not deliver incomplete set'
    assert len(list(fab.glob('*.drl')))>=2, 'Separate PTH/NPTH drills missing'
    assert (fab/'assembly-positions.csv').stat().st_size>0
    assert (out/(NAME+'-Hierarchy.pdf')).read_bytes().startswith(b'%PDF-')
    # Do not invent purchasing identities for generic legacy parts.
    xml=ET.parse(d/'reference/final-netlist.xml');rows=[];unselected=[]
    exact={'D1':('Littelfuse','SMBJ16CA'),'D30':('Nexperia','BZT52H-B15,115'),
           'U21':('Texas Instruments','TMUX1511PWR'),'U22':('Analog Devices','LTC6993HS6-2#TRMPBF'),
           'U23':('Texas Instruments','SN74LVC1G11DBVR'),'U24':('Texas Instruments','TLV803EA30DBZR')}
    exact.update({f'Q{i}':('Diodes Incorporated','DMC3071LVT-7' if i<12 else 'DMG6601LVT-7') for i in range(8,16)})
    for c in xml.findall('.//components/comp'):
        r=c.attrib['ref'];v=c.findtext('value') or '';fields={f.attrib['name']:f.text or '' for f in c.findall('fields/field')}
        maker,mpn=exact.get(r,(fields.get('Manufacturer',''),fields.get('MPN',fields.get('Manufacturer Part Number',''))))
        volts=fields.get('Voltage Rating','') or ('16V' if r in ('C62','C63','C64','C65') else '')
        tolerance=fields.get('Tolerance','') or (re.search(r'\b\d+(?:\.\d+)?%',v).group(0) if re.search(r'\b\d+(?:\.\d+)?%',v) else '')
        status='SPECIFIED — verify procurement/footprint' if mpn else 'UNSELECTED — exact part required before assembly'
        if not mpn:unselected.append(r)
        rows.append([r,v,c.findtext('footprint') or '',maker,mpn,volts,tolerance,status])
    with (out/'BOM.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['Reference','Value','Footprint','Manufacturer','MPN','Minimum voltage rating','Tolerance','Procurement status']);w.writerows(rows)
    board=p.LoadBoard(str(copied));sites=[]
    for t in board.GetTracks():
        if t.GetClass()=='PCB_VIA' and (t.GetPrimaryDrillFilledFlag() or t.GetPrimaryDrillCappedFlag()):
            sites.append(dict(uuid=t.m_Uuid.AsString(),net=t.GetNetname(),x_mm=p.ToMM(t.GetPosition().x),y_mm=p.ToMM(t.GetPosition().y),drill_mm=p.ToMM(t.GetDrillValue()),diameter_mm=p.ToMM(t.GetWidth(p.F_Cu)),filled=t.GetPrimaryDrillFilledFlag(),capped=t.GetPrimaryDrillCappedFlag(),planarization_required=True))
    via=dict(pcbSha256=sha(copied),requirements='Filled, copper capped and planarized; agree fabrication process before order. Ordinary open/tented drills are not equivalent.',sites=sites)
    (fab/'filled-capped-via-sites.json').write_text(json.dumps(via,indent=2)+'\n')
    (ref/'rev-c-filled-capped-via-sites.json').write_text(json.dumps(via,indent=2)+'\n')
    (fab/'MANUFACTURING-NOTES.md').write_text('# Rev C prototype fabrication\n\nFour layers, 110 × 55 mm, nominal 1.6 mm. Confirm actual RF/USB stackup and impedance with fabricator. Use separate PTH/NPTH drill files. Assembly positions are millimetres, both sides, absolute board coordinates. Filled/copper-capped/planarized vias listed in filled-capped-via-sites.json are mandatory; saved drill flags do not themselves specify a fabricator process. Confirm underside microSD/enclosure clearance. This is a local export, not a fabrication order or qualified automotive design.\n')
    mechanical=ref/'rev-c-obd-mechanical-clearance.md'
    if mechanical.exists():
        shutil.copy2(mechanical,fab/mechanical.name)
        shutil.copy2(ref/'rev-c-obd-mechanical-clearance.json',fab/'rev-c-obd-mechanical-clearance.json')
        with (fab/'MANUFACTURING-NOTES.md').open('a') as notes:
            notes.write('\nMounting: M3 socket head, NO washer; checked envelope 5.5 mm diameter by 3 mm high. H1 clearance is 0.7504 mm centered, 0.2504 mm after nominal screw float. Actual tolerance/sample fit remains to be qualified before production assembly. See rev-c-obd-mechanical-clearance.md.\n')
    (ref/'MANUFACTURING-NOTES.md').write_text((fab/'MANUFACTURING-NOTES.md').read_text()+'\nChecked PCB SHA-256: `'+sha(copied)+'`. Processing-site count: '+str(len(sites))+'. See rev-c-filled-capped-via-sites.json for exact coordinates, UUIDs, drill sizes and saved flags.\n')
    (out/'README.md').write_text((HERE/'REV-C-DELIVERY.md').read_text())
    (ref/'rev-c-package-status.json').write_text(json.dumps(dict(revision='C',cad_validation='PASS',pcbSha256=sha(copied),prototype_only=True,automotive_qualified=False,firmware_integration_complete=False,assembly_bom_complete=not unselected,unselected_exact_parts=unselected,external_upload_performed=False),indent=2)+'\n')
    assert all(sha(f)==digest for f,digest in before.items()), 'Source CAD changed during packaging'
    assert all(sha(out/f.name)==digest for f,digest in before.items()), 'Export changed copied CAD'
    # Exercise the delivered portable default in its actual new location.
    run(sys.executable,out/'source/verify_safety_revision.py')
    copied_audit=json.loads((ref/'p1-contract-audit.json').read_text())
    assert copied_audit['releaseGatePassed'] and copied_audit['pcbSha256']==sha(copied)
    # The portable audit creates interpreter caches; omit those from deliverables.
    for cache in out.rglob('__pycache__'):
        shutil.rmtree(cache)
    patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
              rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
              rb'gh[pousr]_[A-Za-z0-9]{30,}',rb'github_pat_[A-Za-z0-9_]{40,}',rb'AKIA[A-Z0-9]{16}']
    files=sorted(f for f in out.rglob('*') if f.is_file())
    findings=[dict(file=f.relative_to(out).as_posix(),pattern=i) for f in files
              for i,pattern in enumerate(patterns) if re.search(pattern,f.read_bytes())]
    assert not findings, 'Credential-like content found; do not archive'
    (ref/'rev-c-package-secret-scan.json').write_text(json.dumps(dict(status='PASS',files_scanned=len(files),credential_pattern_findings=findings,external_upload_performed=False),indent=2)+'\n')
    def checksums(folder):
        files=sorted(f for f in folder.rglob('*') if f.is_file() and f.name!='SHA256SUMS.txt')
        (folder/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+f.relative_to(folder).as_posix()+'\n' for f in files))
    def zip_tree(folder,target):
        with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
            for f in sorted(folder.rglob('*')):
                if f.is_file():z.write(f,folder.name+'/'+f.relative_to(folder).as_posix())
        with zipfile.ZipFile(target) as z:
            assert z.testzip() is None
            for f in folder.rglob('*'):
                if f.is_file():assert z.read(folder.name+'/'+f.relative_to(folder).as_posix())==f.read_bytes()
    checksums(fab);checksums(out);zip_tree(fab,fabzip);zip_tree(out,archive)
    for f in (archive,fabzip):f.with_suffix(f.suffix+'.sha256').write_text(sha(f)+'  '+f.name+'\n')
    print(json.dumps(dict(project=str(out),projectZip=str(archive),fabricationZip=str(fabzip),pcbSha256=sha(pcb),viaSites=len(sites),unselectedParts=len(unselected)),indent=2))

if __name__=='__main__':main()
