"""Native KiCad10 pcbnew creation and deterministic clearance-aware2-layer routing."""
import pcbnew as p
import json, math, heapq, time
from pathlib import Path
HERE=Path(__file__).resolve().parent; OUT=HERE/'design'
data=json.loads((OUT/'design.json').read_text());parts=data['parts']
board=p.BOARD(); board.GetDesignSettings().SetCopperLayerCount(2)
V=lambda x,y:p.VECTOR2I(p.FromMM(x),p.FromMM(y))
W,H=60.,50.; STEP=.25; NX,NY=int(W/STEP)+1,int(H/STEP)+1
nets={n:p.NETINFO_ITEM(board,n,0) for d in parts for n in d['nets'].values()}
for n in sorted(nets):board.Add(nets[n])
fps={}; padmeta=[]
for d in parts:
 lib,name=d['footprint'].split(':',1)
 libpath=OUT/'Carrier.pretty' if lib=='Local' else Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')/(lib+'.pretty')
 fp=p.FootprintLoad(str(libpath),name);assert fp,d['ref'];board.Add(fp);fp.SetReference(d['ref']);fp.SetValue(d['value']);fp.SetPath(p.KIID_PATH('/'+data['sheet_uuid']+'/'+d['uuid']));fp.SetPosition(V(*d['pcb']));fp.SetOrientationDegrees(d['angle']);fps[d['ref']]=fp
 fp.SetFPID(p.LIB_ID(lib,name));
 for key,val in [('MPN',d['mpn']),('Datasheet',d['url'])]:
  fld=p.PCB_FIELD(fp,p.FIELD_T_USER,key);fld.SetText(val);fld.SetVisible(False);fp.Add(fld)
 fp.Reference().SetVisible(False);fp.Value().SetVisible(False);fp.Reference().SetTextSize(V(.9,.9));fp.Reference().SetTextThickness(p.FromMM(.15))
 for pad in fp.Pads():
  no=pad.GetNumber();net=d['nets'].get(no)
  if net:pad.SetNet(nets[net])
  elif no:
   nc='unconnected-('+d['ref']+'-'+({'U1':{'3':'D2','5':'D4','6':'D5','7':'D6','8':'D7'},'J1':{'9':'DET_B','10':'DET_A'}}.get(d['ref'],{}).get(no,no))+'-Pad'+no+')'
   if nc not in nets:nets[nc]=p.NETINFO_ITEM(board,nc,0);board.Add(nets[nc])
   pad.SetNet(nets[nc])
  # Native bounding boxes include local rotation; use conservative pad-body envelope.
  pos=pad.GetPosition();box=pad.GetBoundingBox();
  padmeta.append(dict(ref=d['ref'],no=no,net=net,x=p.ToMM(pos.x),y=p.ToMM(pos.y),x0=p.ToMM(box.GetLeft()),y0=p.ToMM(box.GetTop()),x1=p.ToMM(box.GetRight()),y1=p.ToMM(box.GetBottom()),layers=[z for z,l in enumerate([p.F_Cu,p.B_Cu]) if pad.IsOnLayer(l)],pad=pad))
def line(x1,y1,x2,y2,layer,width=.1):
 s=p.PCB_SHAPE();s.SetShape(p.SHAPE_T_SEGMENT);s.SetStart(V(x1,y1));s.SetEnd(V(x2,y2));s.SetLayer(layer);s.SetWidth(p.FromMM(width));board.Add(s)
for a,b in [((0,0),(W,0)),((W,0),(W,H)),((W,H),(0,H)),((0,H),(0,0))]:line(*a,*b,p.Edge_Cuts,.05)
def text(t,x,y,size=1.,layer=p.F_SilkS):
 q=p.PCB_TEXT(board);q.SetText(t);q.SetPosition(V(x,y));q.SetTextSize(V(size,size));q.SetTextThickness(p.FromMM(.15));q.SetLayer(layer);board.Add(q)
text('CHRYSLER BLE / SD',42,3.5,1.0);text('USB5V ONLY - NO12V',42,6,1.);text('Rev A  /  3.3V LOGIC',30,48.2,.85)
text('STOP / EJECT',13,48.0,.85);text('STATUS',20,34.5,.85)
text('EXT ANTENNA: route cable off board',15,24.5,.72,p.Cmts_User)
# RF radiating antenna is external; reserve carrier upper-left edge as a cable exit; no new RF feedline.
for a,b in [((1,0),(27,0)),((27,0),(27,1)),((27,1),(1,1))]:line(*a,*b,p.Cmts_User,.2)
for a,b in [((-22,2),(-2,2)),((-2,2),(-2,26)),((-2,26),(-22,26)),((-22,26),(-22,2))]:line(*a,*b,p.Cmts_User,.2)
text('EXTERNAL ANTENNA\nOFF-BOARD / NO METAL',-12,14,1.0,p.Cmts_User)
# Build layer/net obstacle maps. All clearances0.20mm; signals0.25mm, power0.40mm.
# Paths are rectilinear to make exact separation auditable.
base=[{} for _ in range(2)]
def mark_rect(x0,y0,x1,y1,layers,owner,pad=.35):
 for ix in range(max(0,int(math.ceil((x0-pad)/STEP))),min(NX,int(math.floor((x1+pad)/STEP))+1)):
  for iy in range(max(0,int(math.ceil((y0-pad)/STEP))),min(NY,int(math.floor((y1+pad)/STEP))+1)):
   for z in layers:base[z].setdefault((ix,iy),set()).add(owner)
for m in padmeta:mark_rect(m['x0'],m['y0'],m['x1'],m['y1'],m['layers'],m['net'],.5 if m['ref'].startswith('H') else .35)
# Include socket manufacturer's copper/track keepout polygons by native absolute coordinate.
for fp in fps.values():
 for z in fp.Zones():
  if not z.GetIsRuleArea() or not z.GetDoNotAllowTracks():continue
  bb=z.GetBoundingBox();print('KEEP',fp.GetReference(),p.ToMM(bb.GetLeft()),p.ToMM(bb.GetTop()),p.ToMM(bb.GetRight()),p.ToMM(bb.GetBottom()),flush=True);mark_rect(p.ToMM(bb.GetLeft()),p.ToMM(bb.GetTop()),p.ToMM(bb.GetRight()),p.ToMM(bb.GetBottom()),[0,1],None,.2)
occupied=[{} for _ in range(2)];routes=[];via_pts=[]
for x,y in [(41,11),(42.5,11),(44,11),(45.5,11),(47,11),(41,9.5),(44,9.5),(47,9.5),(48.5,31.25),(54,28.5)]:
 v=p.PCB_VIA(board);v.SetPosition(V(x,y));v.SetWidth(p.FromMM(.65));v.SetDrill(p.FromMM(.3));v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNet(nets['GND']);board.Add(v);via_pts.append((round(x/STEP),round(y/STEP)))
 mark_rect(x-.325,y-.325,x+.325,y+.325,[0,1],'GND',.35)
# Short surface ground stubs into adjacent vias at socket shield and decoupler.
for a,b in [((47.325,31.275),(48.5,31.25)),((54,29.05),(54,28.5))]:
 tr=p.PCB_TRACK(board);tr.SetStart(V(*a));tr.SetEnd(V(*b));tr.SetWidth(p.FromMM(.4));tr.SetLayer(p.F_Cu);tr.SetNet(nets['GND']);board.Add(tr)
 mark_rect(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1]),[0],'GND',.4)

def blocked(x,y,z,net,via=False):
 if x<3 or y<3 or x>=NX-3 or y>=NY-3:return True
 for own in base[z].get((x,y),()):
  if own!=net:return True
 for own in occupied[z].get((x,y),()):
  if own!=net:return True
 if via:
  if any((x-vx)**2+(y-vy)**2<9 for vx,vy in via_pts):return True
  for xx in range(x-2,x+3):
   for yy in range(y-2,y+3):
    if (xx-x)**2+(yy-y)**2>5:continue
    for zz in (0,1):
     if any(o!=net for o in base[zz].get((xx,yy),())) or any(o!=net for o in occupied[zz].get((xx,yy),())):return True
 return False
def key(m,z=None):return (round(m['x']/STEP),round(m['y']/STEP),m['layers'][0] if z is None else z)
def route(a,b,net):
 starts=[key(a,z) for z in a['layers']];ends={key(b,z) for z in b['layers']}
 def h(t):return min(abs(t[0]-u[0])+abs(t[1]-u[1])+15*(t[2]!=u[2]) for u in ends)
 q=[];dist={};prev={};serial=0
 for t in starts:dist[t]=0;heapq.heappush(q,(h(t),serial,t));serial+=1
 end=None
 while q:
  _,_,t=heapq.heappop(q)
  if t in ends:end=t;break
  x,y,z=t
  for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(0,0)]:
   via=(dx==dy==0);u=(x+dx,y+dy,1-z if via else z)
   if blocked(*u,net,via=via) and u not in ends:continue
   cost=dist[t]+(30 if via else 1)+(0.02 if u[2]==(0 if abs(b['x']-a['x'])>abs(b['y']-a['y']) else 1) else 0)
   if cost+1e-8>=dist.get(u,1e30):continue
   dist[u]=cost;prev[u]=t;heapq.heappush(q,(cost+h(u),serial,u));serial+=1
 if end is None:
  print('DEBUG',net,a,b,'starts',[(t,base[t[2]].get(t[:2])) for t in starts], 'adj',[(u,base[u[2]].get(u[:2])) for u in [(starts[0][0]+dx,starts[0][1]+dy,starts[0][2]) for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]]],flush=True)
  raise RuntimeError('No path '+net+' '+a['ref']+'.'+a['no']+' -> '+b['ref']+'.'+b['no'])
 path=[end]
 while path[-1] not in starts:path.append(prev[path[-1]])
 path.reverse();width=.4 if net in ('USB_5V','SD_3V3','GND') else .25
 def seg(aa,bb,z):
  if aa==bb:return
  tr=p.PCB_TRACK(board);tr.SetStart(V(*aa));tr.SetEnd(V(*bb));tr.SetWidth(p.FromMM(width));tr.SetLayer([p.F_Cu,p.B_Cu][z]);tr.SetNet(nets[net]);board.Add(tr)
 # Tiny pad-centre leadouts remain inside the copper pad.
 seg((a['x'],a['y']),(path[0][0]*STEP,path[0][1]*STEP),path[0][2]);seg((b['x'],b['y']),(path[-1][0]*STEP,path[-1][1]*STEP),path[-1][2])
 start=path[0];lastdir=None
 for j in range(1,len(path)):
  t,u=path[j-1],path[j];direction=(u[0]-t[0],u[1]-t[1],u[2]-t[2])
  if t[2]!=u[2]:
   seg((start[0]*STEP,start[1]*STEP),(t[0]*STEP,t[1]*STEP),t[2]);v=p.PCB_VIA(board);v.SetPosition(V(t[0]*STEP,t[1]*STEP));v.SetWidth(p.FromMM(.65));v.SetDrill(p.FromMM(.3));v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNet(nets[net]);board.Add(v);via_pts.append((t[0],t[1]));start=u;lastdir=None
  else:
   if lastdir is not None and direction!=lastdir:
    seg((start[0]*STEP,start[1]*STEP),(t[0]*STEP,t[1]*STEP),t[2]);start=t
   lastdir=direction
  # Conservative swept-copper obstacle radius includes next track halfwidth+clearance.
  rad=.75 if t[2]!=u[2] else .4+width/2
  for xx in range(u[0]-3,u[0]+4):
   for yy in range(u[1]-3,u[1]+4):
    if ((xx-u[0])*STEP)**2+((yy-u[1])*STEP)**2 <=rad**2:
     for zz in ((0,1) if t[2]!=u[2] else (u[2],)):occupied[zz].setdefault((xx,yy),set()).add(net)
 seg((start[0]*STEP,start[1]*STEP),(path[-1][0]*STEP,path[-1][1]*STEP),path[-1][2]);routes.append(dict(net=net,from_=a['ref']+'.'+a['no'],to=b['ref']+'.'+b['no'],steps=len(path)))
# Route pin-local series pairs first, then SPI, power, low-rate controls, ground.
order=['SD_3V3','USB_5V','MCU_3V3','SD_DAT1','SD_DAT2','SD_MISO','SD_CS','SD_MOSI','SD_SCK','MCU_SCK','MCU_MOSI','MCU_CS','LED_GPIO','LED_A','BUTTON']
for net in order:
 ps=[m for m in padmeta if m['net']==net]; connected=[ps.pop(0)]
 while ps:
  a,b=min(((a,b) for a in connected for b in ps),key=lambda ab:abs(ab[0]['x']-ab[1]['x'])+abs(ab[0]['y']-ab[1]['y']))
  route(a,b,net);connected.append(b);ps.remove(b)
 print('routed',net,flush=True)
# Ground planes, both sides, include broad regulator-tab heat spreading. Fill native, not precomputed artwork.
for layer in [p.F_Cu,p.B_Cu]:
 z=p.ZONE(board);z.SetLayer(layer);z.SetNet(nets['GND']);z.SetLocalClearance(p.FromMM(.25));z.SetPadConnection(p.ZONE_CONNECTION_FULL);z.SetMinThickness(p.FromMM(.2));o=z.Outline();o.NewOutline()
 for x,y in [(1,1),(59,1),(59,49),(1,49)]:o.Append(int(p.FromMM(x)),int(p.FromMM(y)))
 board.Add(z)
p.ZONE_FILLER(board).Fill(board.Zones());p.SaveBoard(str(OUT/'chrysler_ble_sd.kicad_pcb'),board)
(OUT/'routing.json').write_text(json.dumps(dict(routes=routes,tracks=len(list(board.GetTracks())),nets=len(nets),board_mm=[W,H]),indent=2))
print('SAVED native PCB',len(routes),'connections',len(list(board.GetTracks())),'tracks/vias')
