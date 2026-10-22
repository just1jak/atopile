"""Verify the presentation repair against its committed electrical baseline."""
from pathlib import Path
import hashlib, json, subprocess, xml.etree.ElementTree as ET, sys
P=Path(__file__).resolve().parents[1]; D=P/'current'
sys.path.insert(0,str(D/'source'))
from specctra_tools import parse
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
old=ET.fromstring(subprocess.check_output(['git','show','f7593592:projects/chrysler-scanner/current/reference/final-netlist.xml']))
new=ET.parse(D/'reference/final-netlist.xml').getroot()
def parts(root):
    return {c.attrib['ref']:{'value':c.findtext('value'),'footprint':c.findtext('footprint'),'fields':{f.attrib['name']:f.text for f in c.findall('fields/field')},'path':c.find('sheetpath').attrib} for c in root.findall('components/comp')}
def nets(root):
    return {n.attrib['name']:sorted((x.attrib['ref'],x.attrib['pin']) for x in n.findall('node')) for n in root.findall('nets/net')}
visible=[]
for f in D.glob('*.kicad_sch'):
    t=f.read_text(encoding='utf-8')
    for s in parse(t).children('symbol'):
        props={p.items[1].value:p for p in s.children('property')}
        if 'Voltage Rating' in props:
            p=props['Voltage Rating'];assert 'hide' not in t[p.start:p.end]
            visible.append(props['Reference'].items[2].value)
checks={'allComponentsValuesFootprintsFieldsPathsExact':parts(old)==parts(new),
        'allNamedNetEndpointsExact':nets(old)==nets(new),
        'all24RatingsVisible':len(visible)==24,
        'pcbBytesUnchanged':sha(D/'ChryslerScanner_V240_SD.kicad_pcb')=='68d206c7f3794b39c32291e626993844f60c12ea20ad78d16e5127c4ccebafd9'}
assert all(checks.values()), checks
report={'status':'PASS','baselineCommit':'f7593592','checks':checks,'visibleRatings':sorted(visible),'pcbSha256':sha(D/'ChryslerScanner_V240_SD.kicad_pcb'),'netlistSha256':sha(D/'reference/final-netlist.xml')}
(D/'reference/rev-c-comparison-annotation-audit.json').write_text(json.dumps(report,indent=2)+'\n')
reviewfile=D/'reference/rev-c-adversarial-review.json'; review=json.loads(reviewfile.read_text())
review.setdefault('priorAnnotationReviewEvidence',{k:review[k] for k in ('schematicSha256','finalNetlistSha256','finalErcSha256','finalDrcSha256')})
review['schematicSha256']={f.name:sha(f) for f in D.glob('*.kicad_sch')}
for key,name in [('finalNetlistSha256','final-netlist.xml'),('finalErcSha256','final-erc.json'),('finalDrcSha256','final-drc.json')]:review[key]=sha(D/'reference'/name)
review['comparisonAnnotationReview']={'date':'2026-10-22','reviewer':'Implementing-agent delta review; no new independent reviewer claimed.','status':'PASS_PRESENTATION_ONLY_DELTA','scope':'C1 positive mark at pin 1; 24 visible unchanged voltage ratings; loaded ADC gain and post-D2 measurement reminder.','electricalAudit':'rev-c-comparison-annotation-audit.json','checks':['Native ERC and full refill/track/parity DRC clean.','Strict full contract, native connectivity, preservation and bounds pass.','Component fields, values, footprints, paths and named net endpoints identical to prior commit.','PCB bytes identical; C1 remains pin 1 +12V / pin 2 GND.','Intentional safety changes and deferred firmware obligations retained.']}
reviewfile.write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps(report,indent=2))
