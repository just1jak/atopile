"""Independent strict Rev-C contract/preservation audit; never saves CAD.

Run with KiCad Python. First run with --freeze-baseline while current is the
accepted pre-P1 project. The snapshot and explicit removal allowlist are frozen
once and hash-checked thereafter. Final release runs require fresh native XML,
ERC and full DRC; --structural-only is explicitly not a release pass.
"""
from pathlib import Path
import argparse, collections, hashlib, importlib.util, json, shutil, subprocess, sys, uuid
import xml.etree.ElementTree as ET
import pcbnew as p

W = Path(__file__).resolve().parent
P = W.parent.parent
N = 'ChryslerScanner_V240_SD'
BASE_PCB_SHA = '85011cefd33c4d6a623440d91eeb9876282d39dc7fc6a37eb90d50e2a278c36a'
BASE_XML_SHA = '2f6c7cfb93fe8f03df215e366a545ad1a952b55dd2c4e069fa5eda93bd6b7939'
BASE_PRO_SHA = '52183ee48ae18f736465cb24c327b45fca4cb63fdcd560b91ecd7610d4cf692c'
HISTORICAL_SEED_SHA = 'f5b42ba76001f790c445533dfcd8567136b5b018127ac8982a2b04650661a2d1'
BASE_ROOT_SHA = '361be221836ec8b3fa3c332ff0cdd4b08fa1664643b4cf84502c839d3ce75342'
ROOT_UUID = 'b35850f9-3522-5e00-90df-092fcfbfe6bd'
uid = lambda name: str(uuid.uuid5(uuid.NAMESPACE_URL, 'chrysler/rev-c/'+name))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()

# Independent engineering contract, deliberately not learned from candidate CAD.
VALUES = {'D1': 'SMBJ16CA', 'R49': '22k 1%', 'R51': '22k 1%', 'R53': '22k 1%',
          'R65':'8.2k 1%', 'R68':'8.2k 1%', 'R71':'8.2k 1%', 'R74':'8.2k 1%',
          'Q8':'DMC3071LVT-7','Q9':'DMC3071LVT-7','Q10':'DMC3071LVT-7','Q11':'DMC3071LVT-7',
          'Q12':'DMG6601LVT-7','Q13':'DMG6601LVT-7','Q14':'DMG6601LVT-7','Q15':'DMG6601LVT-7'}
VALUES.update({ref:'4.7k 1%' for ref in ('R64','R67','R70','R73')})
VALUES.update({ref:'1.62k 1%' for ref in ('R50','R52','R54')})
# Procurement delta: TTL-input 5 V CCD drivers, identical packages and pins.
VALUES.update({'U17':'74AHCT1G17GV','U18':'SN74AHCT1G14'})
CHANGES = {('U9','5'): ('+12V','PCI_VCC'), ('C11','2'): ('+12V','PCI_VCC'),
           ('R49','1'): ('J1962-16','+12V')}
for old, refs in [('V_BA', ['R49','R50','C47','D27']),
                  ('V_BT', ['R51','R52','C48','D28']),
                  ('V_PR', ['R53','R54','C49','D29'])]:
    for ref in refs:
        CHANGES[(ref, '2' if ref in ('R49','R51','R53') else '1')] = (old, old+'_PRE')
NEW = {
    'U21': ('TMUX1511PWR','Package_SO:TSSOP-14_4.4x5mm_P0.65mm',
            {'1':'LOGIC_PG','2':'V_BA_PRE','3':'V_BA','4':'LOGIC_PG','5':'V_BT_PRE','6':'V_BT','7':'GND','8':'V_PR','9':'V_PR_PRE','10':'LOGIC_PG','11':'GND','12':'GND','13':'GND','14':'+3.3V'}),
    'U22': ('LTC6993HS6-2#TRMPBF','Package_TO_SOT_SMD:TSOT-23-6',
            {'1':'ACT_LED','2':'GND','3':'WD_SET','4':'WD_DIV','5':'+3.3V','6':'HEARTBEAT_VALID'}),
    'U23': ('SN74LVC1G11DBVR','Package_TO_SOT_SMD:SOT-23-6',
            {'1':'EN','2':'GND','3':'LOGIC_PG','4':'N_R88_2','5':'+3.3V','6':'HEARTBEAT_VALID'}),
    'U24': ('TLV803EA30DBZR','Package_TO_SOT_SMD:SOT-23-3',
            {'1':'GND','2':'LOGIC_PG','3':'+3.3V'}),
    'D30': ('BZT52H-B15','Diode_SMD:D_SOD-123F', {'1':'PCI_VCC','2':'GND'}),
}
for ref, value, left, right, footprint in [
    ('R115','100k 0.1% 25ppm','WD_SET','GND','R_0603_1608Metric'),
    ('R116','191k 1%','+3.3V','WD_DIV','R_0603_1608Metric'),
    ('R117','100k 1%','WD_DIV','GND','R_0603_1608Metric'),
    ('R118','10k 1%','ACT_LED','GND','R_0603_1608Metric'),
    ('R119','10k 1%','+3.3V','LOGIC_PG','R_0603_1608Metric'),
    ('R120','100k 1%','V_BA','GND','R_0603_1608Metric'),
    ('R121','100k 1%','V_BT','GND','R_0603_1608Metric'),
    ('R122','100k 1%','V_PR','GND','R_0603_1608Metric'),
    ('R123','1k 1W 1%','+12V','PCI_VCC','R_2512_6332Metric')]:
    NEW[ref] = (value, 'Resistor_SMD:'+footprint, {'1':left, '2':right})
for ref in ('C62','C63','C64','C65'):
    NEW[ref] = ('100nF 16V X7R','Capacitor_SMD:C_0603_1608Metric', {'1':'+3.3V','2':'GND'})
# User-authorized debug access: electrical endpoints fixed independently of CAD.
TP_UID=lambda name:str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/testpoints/'+name))
TP_NETS='J1962-16 +12V VBUS +5V +3.3V SD_3V3 +7.5V VBB VPP PCI_VCC J1962-2 J1962-3 J1962-11 J1962-6 J1962-12 J1962-14 J1962-9 J1962-7 J1962-15 TX0 RX0 EN IO0 SCL SDA PCI_RX PCI_TX RX1 TX1 RX2 TX2 ACT_LED HEARTBEAT_VALID LOGIC_PG N_R88_2 V_BA_PRE V_BA V_BT_PRE V_BT V_PR_PRE V_PR SD_DETECT CCD+ CCD- SD_CS SD_SCK SD_MOSI SD_MISO GND GND GND GND'.split()
TP_REFS={'TP'+str(i) for i in range(1,53)}
for i,net in enumerate(TP_NETS,1):
    NEW['TP'+str(i)]=(net,'footprints:'+('TestPoint_Pad_D1.0mm' if 45<=i<=48 else 'TestPoint_Keystone_5015_Micro_Mini'),{'1':net})
RATINGS = {ref: rating for rating, refs in [
    ('50V', 'C1 C4 C13 C16 C20 C14 C15'), ('100V','C5 C17 C21'),
    ('25V','C6 C7 C8 C9 C10 C18 C19 C22 C23 C24'), ('10V','C26 C27 C35 C56')]
    for ref in refs.split()}
SUPPLY_CUT = set('''0b444175-e675-468c-91ec-b4d5e210f2f5
10cec695-bbfa-4974-b5da-a7d60d9ca124
2352aa0e-7ee1-497b-9a11-bf5103725cf1
2bf621f2-682b-4ac9-a720-42f6809d6966
305858b2-cf89-400b-958c-3e7d96c5ec94
453979fa-7516-4842-9410-ad0e54551876
74117d98-783a-4d45-8455-848ffac9b24d
77b6ca39-ae65-4776-9d63-187412fd2f03
8ca16d9b-3138-43c8-9cda-550abdec7b1d
94c99082-bcf7-4e23-8eb8-393e7d932c86
96d27932-176c-4b5f-8cc6-fcd1092c859f
98e4dd49-d735-44e4-94bd-288808bc04d8
a23a8118-e502-4d6b-8448-4ec2729be158
b5701d16-8373-4839-9418-f3d4914b7fe7
c5cf788e-813a-430a-8800-9eddb12360d5
f1ac5acb-77c1-44d8-92af-52d898102281
f5571307-79d8-4743-93d4-89493606e456'''.split())
RESTORED_ADC = set('''0501bb2d-e50c-44df-bb67-d96eadb5aa67
09fa8030-4f87-508a-b7ff-a6f502b02cad
11a72a34-975a-41c1-8b8a-d8807089d28c
1557548c-9a5f-4208-91b5-7f98133ef34a
285f63de-5ebe-4598-a332-dcd97560700a
29001eb4-ae4a-4a35-95bf-8a3e1edd5108
3df53947-21e0-4d44-8f45-37993b02e739
4b21ae8b-3709-443e-934e-57384bc8cbd9
59b90ad7-0977-4f52-84a0-ecceb2380fa5
660b46aa-0e74-4971-ab89-bd749bac688c
6d4bd82f-97c6-4134-9861-42d08b2c27ac
7369fdce-48b6-43b2-91cc-9accc5e7de18
913e7d48-6bb1-431c-8e90-23d261ec1722
9662e04c-6f05-4ed7-b88a-2fb177353bcd
a2c1bf3e-6c76-4430-9526-ce3b4115aed5
a3d1298d-3812-40ce-9de4-78ffc906a6c4
b3c3ad46-20ee-48e7-8992-c4055020cfe6
b89b0ed6-a763-4e83-9dbd-10ec4f035ae1
bc12b6c6-6823-4f53-a88c-eb345d042f5f
cdc7cc2b-aa02-4478-b602-b7c4a086916b
d2739e92-17fe-4e5a-94f2-50752a63ad9d
e8b935ce-0e28-45d7-baba-b31dc51fd7d3
e9544cd2-b889-412b-a5ee-206fab556955
fb4b5436-0e5c-46ac-8750-f56b3caa8025'''.split())
PROTECTED_ADC_EXCEPTIONS = {'8cf8242f-4b46-50a7-a351-4b51bd98f7f7'}
ALLOWED_NEW_NETS = set('''GND +3.3V +12V EN PCI_VCC V_BA V_BT V_PR
V_BA_PRE V_BT_PRE V_PR_PRE N_R88_2 WD_SET WD_DIV LOGIC_PG
ACT_LED HEARTBEAT_VALID'''.split())

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate',type=Path,default=W.parent if W.name=='source' else W/'candidate')
parser.add_argument('--xml',type=Path)
parser.add_argument('--erc',type=Path)
parser.add_argument('--drc',type=Path)
parser.add_argument('--report',type=Path)
parser.add_argument('--freeze-baseline',action='store_true')
parser.add_argument('--structural-only',action='store_true')
args = parser.parse_args()
D = args.candidate.resolve()
F = D/'reference/pre-p1'
if args.freeze_baseline:
    accepted = P/'current'
    expected = {N+'.kicad_pcb':BASE_PCB_SHA, N+'.kicad_pro':BASE_PRO_SHA,
                'final-netlist.xml':BASE_XML_SHA}
    F.mkdir(parents=True,exist_ok=True)
    for name, digest in expected.items():
        source = accepted/('reference/'+name if name=='final-netlist.xml' else name)
        assert sha(source)==digest, ('Accepted baseline changed; investigate before freezing', source)
        target = F/name
        if target.exists(): assert sha(target)==digest, ('Frozen baseline changed', target)
        else: shutil.copy2(source,target)
    # Preserve the prior Git project separately: current user/KiCad metadata has
    # changed since HEAD, so restoring HEAD silently would lose that state.
    previous = subprocess.check_output(['git','-c','safe.directory='+str(P.parents[1]),
                                        'show','9399c5f9:projects/chrysler-scanner/current/'+N+'.kicad_pro'])
    target = F/(N+'-git-9399c5f9.kicad_pro')
    if not target.exists():target.write_bytes(previous)
    root_before = subprocess.check_output(['git','-c','safe.directory='+str(P.parents[1]),
        'show','9399c5f9:projects/chrysler-scanner/current/'+N+'.kicad_sch'])
    assert hashlib.sha256(root_before).hexdigest()==BASE_ROOT_SHA
    target=F/(N+'-root-before.kicad_sch')
    if target.exists():assert sha(target)==BASE_ROOT_SHA
    else:target.write_bytes(root_before)
    historical = accepted/'reference/accepted-input.kicad_pcb'
    assert sha(historical)==HISTORICAL_SEED_SHA
    target=F/'historical-routing-seed.kicad_pcb'
    if target.exists():assert sha(target)==HISTORICAL_SEED_SHA
    else:shutil.copy2(historical,target)
assert F.is_dir(), 'First run with --freeze-baseline while current is accepted'

sp = importlib.util.spec_from_file_location('independent_sexp', D/'source/specctra_tools.py')
s = importlib.util.module_from_spec(sp);sys.modules[sp.name]=s;sp.loader.exec_module(s)
sp = importlib.util.spec_from_file_location('independent_cad_audit', D/'source/audit_routed_board.py')
audit = importlib.util.module_from_spec(sp);sp.loader.exec_module(audit)
errors=[];checks={}
def check(key, ok, detail=None):
    checks[key]=bool(ok)
    if not ok:errors.append({'check':key,'detail':detail})
for name,digest in [(N+'.kicad_pcb',BASE_PCB_SHA),(N+'.kicad_pro',BASE_PRO_SHA),('final-netlist.xml',BASE_XML_SHA)]:
    check('frozenHash:'+name,sha(F/name)==digest)
assert all(checks.values()), errors
check('frozenHistoricalRoutingSeedHash',sha(F/'historical-routing-seed.kicad_pcb')==HISTORICAL_SEED_SHA)
check('frozenRootHierarchyHash',sha(F/(N+'-root-before.kicad_sch'))==BASE_ROOT_SHA)
target = D/(N+'.kicad_pcb');initial_hash=sha(target)
base = p.LoadBoard(str(F/(N+'.kicad_pcb')))
candidate = p.LoadBoard(str(target))
subprocess.run([sys.executable,str(D/'source/verify_c61_top.py')],check=True)
subprocess.run([sys.executable,str(D/'source/verify_testpoints.py')],check=True)
oldcu = {audit.uid(t):t for t in base.GetTracks()}
newcu = {audit.uid(t):t for t in candidate.GetTracks()}
adc_cut = {key for key,t in oldcu.items() if t.GetNetname() in ('V_BA','V_BT','V_PR')}
allowed_cut = (adc_cut-RESTORED_ADC)|SUPPLY_CUT
check('exact24RestoredAdcObjects',len(RESTORED_ADC)==24 and RESTORED_ADC<=adc_cut)
check('exactly62AdcObjectsInFrozenBaseline',len(adc_cut)==62)
check('supplyCutBelongsToFrozenSupplyNets',SUPPLY_CUT<=oldcu.keys() and all(oldcu[k].GetNetname() in ('J1962-16','+12V') for k in SUPPLY_CUT))
check('onlyOneDeclaredProtectedAdcException',
      {k for k in allowed_cut if oldcu[k].IsLocked()}==PROTECTED_ADC_EXCEPTIONS)
contract_file=F/'allowed-copper-removals-final55.json'
contract={key:dict(net=oldcu[key].GetNetname(),locked=oldcu[key].IsLocked()) for key in sorted(allowed_cut)}
if args.freeze_baseline and not contract_file.exists():contract_file.write_text(json.dumps(contract,indent=2),newline='\n')
check('frozenRemovalManifestUnchanged',json.loads(contract_file.read_text())==contract)
manifest=json.loads((D/'reference/p1-remediation-manifest.json').read_text())
check('builderRemovalListExactlyMatchesFrozenContract',
      {t['uuid'] for t in manifest['removedTracks']}==adc_cut and
      set(manifest['removedSupplyBranchIds'])==SUPPLY_CUT)

TP_FILL_MANIFEST=D/'reference/rev-c-testpoint-processing-upgrades.json'
check('testpointProcessingUpgradeManifestFrozen',sha(TP_FILL_MANIFEST)=='0d04ef671bc2f879f0546d53292870b63a8223326edd5052e29732762198e5bc')
TP_FILL_IDS={v['uuid'] for v in json.loads(TP_FILL_MANIFEST.read_text())['sites']}
check('only22DeclaredExistingViasUpgradedForNewPads',len(TP_FILL_IDS)==22 and all(k in oldcu and k in newcu and newcu[k].GetClass()=='PCB_VIA' and newcu[k].GetPrimaryDrillFilledFlag() and newcu[k].GetPrimaryDrillCappedFlag() for k in TP_FILL_IDS))

def copper(t):
    result=dict(kind=t.GetClass(),net=t.GetNetname(),start=audit.xy(t.GetStart()),end=audit.xy(t.GetEnd()),
                width=t.GetWidth(p.F_Cu) if t.GetClass()=='PCB_VIA' else t.GetWidth(),layer=t.GetLayer(),locked=t.IsLocked())
    if t.GetClass()=='PCB_VIA':
        result.update(drill=t.GetDrillValue(),type=int(t.GetViaType()),top=t.TopLayer(),bottom=t.BottomLayer(),
                      filled=t.GetPrimaryDrillFilledFlag(),capped=t.GetPrimaryDrillCappedFlag(),
                      frontTenting=int(t.GetFrontTentingMode()),backTenting=int(t.GetBackTentingMode()))
    if t.GetClass()=='PCB_ARC':result['mid']=audit.xy(t.GetArcMid())
    if audit.uid(t) in TP_FILL_IDS:result.update(filled=True,capped=True)
    return result
C61_CUT={'b2e77e8c-5db9-4c4b-b5df-6fa86e1b60ba','ba39bf73-e299-4de0-a91a-89bb4415e8a3'}
check('c61CutsOnlyUnlockedSdSupplyBranch',all(oldcu[k].GetNetname()=='SD_3V3' and not oldcu[k].IsLocked() for k in C61_CUT))
missing=set(oldcu)-set(newcu)
check('only55SafetyAndTwoC61ExplicitCopperRemovals',missing==allowed_cut|C61_CUT,sorted(missing^(allowed_cut|C61_CUT)))
changed_copper=[key for key in oldcu.keys()&newcu.keys() if copper(oldcu[key])!=copper(newcu[key])]
check('allRetainedOldCopperGeometryExactWith22DeclaredProcessingUpgrades',not changed_copper,changed_copper)
protected={key for key,t in oldcu.items() if t.IsLocked()}-PROTECTED_ADC_EXCEPTIONS
check('all380CurrentlyLockedRetainedObjectsExact',len(protected)==380 and all(key in newcu and copper(oldcu[key])==copper(newcu[key]) for key in protected))
historical=p.LoadBoard(str(F/'historical-routing-seed.kicad_pcb'))
historical_protected={audit.uid(t) for t in historical.GetTracks() if t.IsLocked()}-PROTECTED_ADC_EXCEPTIONS
check('all173HistoricalProtectedObjectsRetainedExactly',len(historical_protected)==173 and
      all(key in newcu and copper(oldcu[key])==copper(newcu[key]) for key in historical_protected))
added=set(newcu)-set(oldcu)
check('newCopperOnlyOnExplicitSafetyNets',all(newcu[key].GetNetname() in (ALLOWED_NEW_NETS|set(TP_NETS)) for key in added),
      sorted({newcu[key].GetNetname() for key in added}-(ALLOWED_NEW_NETS|set(TP_NETS))))
check('noSignalsOnInnerGroundReference',all(t.GetNetname()=='GND' or t.GetLayer()!=p.In1_Cu for t in candidate.GetTracks() if t.GetClass()!='PCB_VIA'))
check('minimumTrackWidth150um',all(t.GetWidth()>=150000 for t in candidate.GetTracks() if t.GetClass()!='PCB_VIA'))
check('onlyFourValidCopperLayers',all(t.GetLayer() in (p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu) for t in candidate.GetTracks() if t.GetClass()!='PCB_VIA'))

def parts_xml(path):
    root=ET.parse(path)
    values={c.attrib['ref']:c.findtext('value') for c in root.findall('.//components/comp')}
    pins={(v.attrib['ref'],v.attrib['pin']):None if n.attrib['name'].startswith('unconnected-') else n.attrib['name']
          for n in root.findall('.//nets/net') for v in n.findall('node')}
    paths={c.attrib['ref']:(c.find('sheetpath').attrib['tstamps'],c.findtext('tstamps')) for c in root.findall('.//components/comp')}
    fields={c.attrib['ref']:{f.attrib['name']:f.text for f in c.findall('fields/field')} for c in root.findall('.//components/comp')}
    return root,values,pins,paths,fields
xml=args.xml or D/'reference/final-netlist.xml'
oldxml,oldvalues,oldpins,oldpaths,_=parts_xml(F/'final-netlist.xml')
newxml,newvalues,newpins,newpaths,fields=parts_xml(xml)
expected_values=dict(oldvalues);expected_values.update(VALUES);expected_values.update({ref:v[0] for ref,v in NEW.items()})
expected_pins=dict(oldpins)
for key,(before,after) in CHANGES.items():assert expected_pins[key]==before, ('Frozen old-pin contract mismatch',key);expected_pins[key]=after
for ref,data in NEW.items():expected_pins.update({(ref,pin):net for pin,net in data[2].items()})
pin_differences=[dict(reference=ref,pin=pin,expected=expected_pins.get((ref,pin)),actual=newpins.get((ref,pin))) for ref,pin in expected_pins.keys()|newpins.keys() if (ref,pin) not in expected_pins or (ref,pin) not in newpins or expected_pins.get((ref,pin))!=newpins.get((ref,pin))]
check('exact329ComponentsIncluding52TestPointsAnd23ExistingValueChanges',len(newvalues)==329 and newvalues==expected_values,
      sorted(ref for ref in expected_values.keys()|newvalues.keys() if expected_values.get(ref)!=newvalues.get(ref)))
check('exact40NoConnectAnd162ConnectedNets',sum(net is None for net in newpins.values())==40 and len({net for net in newpins.values() if net is not None})==162)
check('exact15ExistingPinChangesAnd18NewPinContracts',not pin_differences,pin_differences)
check('originalComponentPathsAndSymbolUuidsPreserved',all(newpaths.get(ref)==path for ref,path in oldpaths.items()))
check('newComponentSymbolsMatchSafetyHierarchy',all(newpaths.get(ref)==(('/'+TP_UID('sheet')+'/',TP_UID(ref+'/symbol')) if ref in TP_REFS else ('/'+uid('safety-sheet')+'/',uid(ref))) for ref in NEW))
check('all24RecoveredVoltageRatingsWithTwoExplicitUpgrades',all(fields.get(ref,{}).get('Voltage Rating')==rating for ref,rating in RATINGS.items()),
      {ref:fields.get(ref,{}).get('Voltage Rating') for ref,rating in RATINGS.items() if fields.get(ref,{}).get('Voltage Rating')!=rating})
sd_pins={'5':'SD_MISO','6':'LOG_BUTTON','7':'SD_DETECT','21':'MCU_SD_CS','27':'MCU_SD_MOSI','38':'MCU_SD_SCK','20':'ACT_LED','24':'TX2','23':'IO0'}
check('frozenSdAndBootPinMapping',all(newpins.get(('U10',pin))==net for pin,net in sd_pins.items()) and ('U10','22') in newpins and newpins[('U10','22')] is None)

# Native sheet interfaces are checked independently of the netlist's global
# aliases: no removed circuit page or extra/mismatched hierarchy port is allowed.
def property_value(node,name):return next(v.items[2].value for v in node.children('property') if v.items[1].value==name)
def sheets(root):return {property_value(node,'Sheetfile'):node for node in root.children('sheet')}
before_root=s.parse((F/(N+'-root-before.kicad_sch')).read_text())
after_root=s.parse((D/(N+'.kicad_sch')).read_text())
before_sheets=sheets(before_root);after_sheets=sheets(after_root)
expected_files=set(before_sheets)|{'23_hardware-safety.kicad_sch','24_debug-testpoints.kicad_sch'}
check('exact23ChildSheetsAnd24NativeSchematicFiles',len(after_sheets)==23 and set(after_sheets)==expected_files and len(list(D.glob('*.kicad_sch')))==24)
check('rootSchematicUuidPreserved',s.atom(s.one(before_root,'uuid'))==s.atom(s.one(after_root,'uuid'))==ROOT_UUID)
interface_renames={'02_pci.kicad_sch':{'+12V':'PCI_VCC'},
                   '17_adc.kicad_sch':{'V_BA':'V_BA_PRE','V_BT':'V_BT_PRE','V_PR':'V_PR_PRE','J1962-16':'+12V'}}
expected_interfaces={name:sorted(interface_renames.get(name,{}).get(pin.items[1].value,pin.items[1].value) for pin in sh.children('pin')) for name,sh in before_sheets.items()}
expected_interfaces['23_hardware-safety.kicad_sch']=sorted(['+3.3V','+12V','PCI_VCC','V_BA_PRE','V_BT_PRE','V_PR_PRE','V_BA','V_BT','V_PR','ACT_LED','EN','N_R88_2'])
expected_interfaces['24_debug-testpoints.kicad_sch']=[]

def semantic(n):return [semantic(v) if isinstance(v,s.Scope) else v.value for v in n.items]
def page(sh):return s.atom(s.one(s.one(s.one(s.one(sh,'instances'),'project'),'path'),'page'))
interfaces_ok=True;old_frames_ok=True;port_count=0
for filename in expected_files:
    sh=after_sheets.get(filename)
    if sh is None:interfaces_ok=False;continue
    pins=[node.items[1].value for node in sh.children('pin')];port_count+=len(pins)
    child=s.parse((D/filename).read_text())
    labels=[node.items[1].value for node in child.children('hierarchical_label')]
    interfaces_ok &= sorted(pins)==sorted(labels)==expected_interfaces[filename] and len(set(pins))==len(pins)
    if filename in before_sheets:
        old=before_sheets[filename]
        old_frames_ok &= all(semantic(s.one(old,key))==semantic(s.one(sh,key)) for key in ('uuid','at','size','instances'))
        old_frames_ok &= property_value(old,'Sheetname')==property_value(sh,'Sheetname')
        for oldpin in old.children('pin'):
            ident=s.atom(s.one(oldpin,'uuid'))
            newpin=next((pin for pin in sh.children('pin') if s.atom(s.one(pin,'uuid'))==ident),None)
            old_frames_ok &= newpin is not None and newpin.items[1].value==interface_renames.get(filename,{}).get(oldpin.items[1].value,oldpin.items[1].value)
    else:old_frames_ok &= (s.atom(s.one(sh,'uuid'))==TP_UID('sheet') and page(sh)=='24') if filename=='24_debug-testpoints.kicad_sch' else (s.atom(s.one(sh,'uuid'))==uid('safety-sheet') and page(sh)=='23')
check('exact168NativePortsAndMatchingChildLabels',interfaces_ok and port_count==168)
check('allOriginalSheetFramesPagesAndPortUuidsPreserved',old_frames_ok)
check('all24PagesNumberedExactlyOnce',sorted(int(page(sh)) for sh in after_sheets.values())==list(range(2,25)) and s.atom(s.one(s.one(after_root,'sheet_instances'),'path'))=='/')

def fpid(f):
    lib=f.GetFPID()
    return str(lib.GetLibNickname())+':'+str(lib.GetLibItemName())

def footprints(board):
    native=audit.native_footprints(board)
    for f in board.GetFootprints():
        item=native[audit.uid(f)];item.update(path=f.GetPath().AsString(),fpid=fpid(f),attributes=f.GetAttributes(),
            models=[(m.m_Filename,[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],[m.m_Scale.x,m.m_Scale.y,m.m_Scale.z],[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z]) for m in f.Models()])
        for pad in f.Pads():
            item['pads'][audit.uid(pad)].update(roundRectRatio=pad.GetRoundRectRadiusRatio(),maskMargin=str(pad.GetLocalSolderMaskMargin()))
    return native
oldfp=footprints(base)
# User-authorized single placement exception; expected geometry is derived from
# the unchanged frozen footprint using this exact transform, never the candidate.
c61base=base.FindFootprintByReference('C61')
c61base.Flip(c61base.GetPosition(),False)
c61base.SetOrientationDegrees(90)
c61base.SetPosition(p.VECTOR2I(193000000,127000000))
c61expected=footprints(base)[audit.uid(c61base)]
newfp=footprints(candidate)
fp_differences=[]
for key,old in oldfp.items():
    expected=json.loads(json.dumps(old));ref=old['reference']
    if ref=='C61':expected=json.loads(json.dumps(c61expected))
    expected['value']=VALUES.get(ref,old['value'])
    for pad in expected['pads'].values():
        if (ref,pad['number']) in CHANGES:pad['net']=CHANGES[ref,pad['number']][1]
    actual=json.loads(json.dumps(newfp.get(key)))
    if actual!=expected:fp_differences.append(ref)
check('all263FootprintsExactWithOnlyDeclaredC61TopTransform',not fp_differences,fp_differences)
fps={f.GetReference():f for f in candidate.GetFootprints()}
check('exactly18SafetyAnd52TestpointFootprintsAdded',len(newfp)==333 and set(fps)=={f.GetReference() for f in base.GetFootprints()}|set(NEW))
# Same-net pads can conceal a physical package collision from electrical DRC.
# Conservatively test bodies/courtyards (native non-text bounding boxes) only
# where this revision adds or actually moves a footprint. Original unchanged
# pairs retain their pre-existing acceptance and are not reclassified here.
baseline_by_ref={v['reference']:v for v in oldfp.values()}
moved_refs={v['reference'] for v in newfp.values() if v['reference'] in baseline_by_ref and
            (v['position']!=baseline_by_ref[v['reference']]['position'] or
             v['orientation']!=baseline_by_ref[v['reference']]['orientation'] or
             v['layer']!=baseline_by_ref[v['reference']]['layer'])}
changed_bodies=set(NEW)|moved_refs
body_collisions=[];seen_pairs=set()
for ref in sorted(changed_bodies):
    f=fps.get(ref)
    if f is None:continue
    a=f.GetBoundingBox(False,False)
    for other,g in fps.items():
        pair=tuple(sorted((ref,other)))
        if other==ref or pair in seen_pairs or f.GetLayer()!=g.GetLayer():continue
        seen_pairs.add(pair);b=g.GetBoundingBox(False,False)
        overlap_x=min(a.GetRight(),b.GetRight())-max(a.GetLeft(),b.GetLeft())
        overlap_y=min(a.GetBottom(),b.GetBottom())-max(a.GetTop(),b.GetTop())
        if overlap_x>0 and overlap_y>0:
            body_collisions.append(dict(references=pair,overlapNm=[overlap_x,overlap_y]))
check('allNewAndMovedBodiesClearOfSameSideParts',not body_collisions,body_collisions)
check('allNewFootprintValuesLibrariesAndPinsExact',all(
    ref in fps and fps[ref].GetValue()==data[0] and fpid(fps[ref])==data[1] and
    {q.GetNumber():q.GetNetname() for q in fps[ref].Pads() if q.GetNumber()}==data[2]
    for ref,data in NEW.items()))
pcb_pins={(f.GetReference(),q.GetNumber()):None if q.GetNetname().startswith('unconnected-') else q.GetNetname() for f in candidate.GetFootprints() if f.GetReference() in newvalues for q in f.Pads() if q.GetNumber()}
check('completeNativeSchematicPcbEndpointParity',pcb_pins==newpins)
check('pcbVoltageRatingFieldsExact',all(fps[ref].GetField('Voltage Rating') and fps[ref].GetField('Voltage Rating').GetText()==rating for ref,rating in RATINGS.items()))
ccd_parts={'U17':('Nexperia','74AHCT1G17GVH'),'U18':('Texas Instruments','SN74AHCT1G14DBVR')}
check('exactTtlInputCcdDriverProcurement',all(
    fps[ref].GetField('Manufacturer') and fps[ref].GetField('Manufacturer').GetText()==maker and
    fps[ref].GetField('MPN') and fps[ref].GetField('MPN').GetText()==mpn
    for ref,(maker,mpn) in ccd_parts.items()))
xml_components={c.attrib['ref']:c for c in ET.parse(xml).findall('components/comp')}
check('schematicCcdProcurementMatchesPcb',all(
    {v.attrib['name']:v.text for v in xml_components[ref].findall('fields/field')}.get('MPN')==mpn and
    {v.attrib['name']:v.text for v in xml_components[ref].findall('fields/field')}.get('Manufacturer')==maker
    for ref,(maker,mpn) in ccd_parts.items()))

check('allNineZoneDefinitionsKeepoutsAndSettingsExact',
      len(list(candidate.Zones()))==9 and {audit.uid(z):audit.zone_signature(z) for z in base.Zones()}=={audit.uid(z):audit.zone_signature(z) for z in candidate.Zones()})
def outlines(board):return {audit.uid(t):(int(t.GetShape()),audit.xy(t.GetStart()),audit.xy(t.GetEnd()),audit.xy(t.GetArcMid()),t.GetWidth()) for t in board.GetDrawings() if t.GetLayer()==p.Edge_Cuts}
check('exactOriginalOutlineAndMountingHoles',outlines(base)==outlines(candidate) and not any(ref in fp_differences for ref in ('H1','H2','H3','H4')))
def setup(path):
    text=path.read_text();node=s.one(s.parse(text),'setup')
    def semantic(n):return [semantic(v) if isinstance(v,s.Scope) else v.value for v in n.items]
    return semantic(node)
# Entirely off-board objects can evade edge-clearance checks. Prove the
# preserved outline is convex, then require every corner of each conservative
# native geometry bounding box inside its rounded polygon (no overhang waiver
# for any added object). Native DRC separately enforces positive edge clearance.
board_polygon=p.SHAPE_POLY_SET()
outline_ok=base.GetBoardPolygonOutlines(board_polygon,False)
convex=False
if outline_ok and board_polygon.OutlineCount()==1 and board_polygon.HoleCount(0)==0:
    chain=board_polygon.COutline(0)
    points=[chain.CPoint(k) for k in range(chain.PointCount())]
    signs=set()
    for k in range(len(points)):
        a,b,c=points[k-2],points[k-1],points[k]
        cross=(b.x-a.x)*(c.y-b.y)-(b.y-a.y)*(c.x-b.x)
        if cross:signs.add(1 if cross>0 else -1)
    convex=len(signs)==1
check('preservedBoardOutlineSingleConvexPolygon',convex)
def bbox_inside(box):
    return convex and all(board_polygon.Contains(p.VECTOR2I(x,y))
        for x in (box.GetLeft(),box.GetRight()) for y in (box.GetTop(),box.GetBottom()))
offboard=[]
for ref in NEW:
    f=fps.get(ref)
    if f is None:offboard.append(ref+':missing');continue
    if not bbox_inside(f.GetBoundingBox(False,False)):offboard.append(ref+':body')
    for q in f.Pads():
        if not bbox_inside(q.GetBoundingBox()):offboard.append(ref+'.'+q.GetNumber()+':pad')
for key in added:
    if not bbox_inside(newcu[key].GetBoundingBox()):offboard.append(key+':copper')
check('allNewBodiesPadsTracksAndViasInsidePreservedOutline',not offboard,offboard)

check('boardSetupAndStackupExact',setup(F/(N+'.kicad_pcb'))==setup(target))
check('projectRulesSeveritiesAndMetadataByteIdenticalToAcceptedCurrent',sha(D/(N+'.kicad_pro'))==BASE_PRO_SHA)

# New drills that intersect an SMD copper aperture need the saved processing
# requirements that the original package already mandated; tenting is not fill.
smdups=[]
all_smd_vias=[]
smd_shapes=[(f.GetReference()+'.'+q.GetNumber(),q.GetEffectiveShape(layer)) for f in candidate.GetFootprints() for q in f.Pads() if q.GetAttribute()==p.PAD_ATTRIB_SMD for layer in (p.F_Cu,p.B_Cu) if q.IsOnLayer(layer)]
for key in newcu:
    t=newcu[key]
    if t.GetClass()!='PCB_VIA':continue
    hole=t.GetEffectiveHoleShape();overlaps=[]
    overlaps=sorted({label for label,shape in smd_shapes if p.SHAPE.Collide(hole,shape,0)})
    if overlaps:
        item=dict(uuid=key,pads=overlaps,filled=t.GetPrimaryDrillFilledFlag(),capped=t.GetPrimaryDrillCappedFlag())
        all_smd_vias.append(item)
        if key in added:smdups.append(item)
check('allSmdIntersectingDrillsFilledAndCapped',all(v['filled'] and v['capped'] for v in all_smd_vias),[v for v in all_smd_vias if not(v['filled'] and v['capped'])])

connection=None
if not args.structural_only:
    drc_path=args.drc or D/'reference/final-drc.json';erc_path=args.erc or D/'reference/final-erc.json'
    drc=json.loads(drc_path.read_text());erc=json.loads(erc_path.read_text())
    check('freshFullNativeDrcClean',all(not drc[k] for k in ('violations','unconnected_items','schematic_parity')) and {'error','warning','exclusion'}<=set(drc['included_severities']) and drc_path.stat().st_mtime_ns>=target.stat().st_mtime_ns)
    latest_sch=max(f.stat().st_mtime_ns for f in D.glob('*.kicad_sch'))
    check('freshNativeErcClean',not any(sh['violations'] for sh in erc['sheets']) and erc_path.stat().st_mtime_ns>=latest_sch)
    check('freshNativeXml',xml.stat().st_mtime_ns>=latest_sch)
    connection=audit.connectivity(candidate)
    check('allNativePadPartitionsAndUncappedAirwiresConnected',not connection['disconnectedNetGroups'] and connection['fullNativeAirwires']==0,connection)
    check('allGroundPadsOneConnectedGroup',connection['ground']['connectedGroupCount']==1)
check('auditDidNotModifyBoard',sha(target)==initial_hash)
report=dict(status='PASS' if all(checks.values()) else 'FAIL',releaseGatePassed=not args.structural_only and all(checks.values()),
            phase='structural_contract_only' if args.structural_only else 'full_release_gate',
            pcbSha256=initial_hash,netlistSha256=sha(xml),baselinePcbSha256=BASE_PCB_SHA,
            baselineProjectSha256=BASE_PRO_SHA,checks=checks,errors=errors,
            allowedCopperRemovalCount=len(allowed_cut),c61AdditionalCopperRemovalCount=len(C61_CUT),protectedCopperRemovalExceptions=sorted(PROTECTED_ADC_EXCEPTIONS),
            retainedProtectedCopperCount=len(protected),retainedHistoricalProtectedCopperCount=len(historical_protected),
            newCopperCount=len(added),nativeHierarchyPortCount=port_count,newSmdViaProcessing=smdups,allSmdViaProcessing=all_smd_vias,connectivity=connection)
out=args.report or D/'reference/p1-contract-audit.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),newline='\n')
print(json.dumps(dict(status=report['status'],releaseGatePassed=report['releaseGatePassed'],phase=report['phase'],failures=errors,report=str(out)),indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
