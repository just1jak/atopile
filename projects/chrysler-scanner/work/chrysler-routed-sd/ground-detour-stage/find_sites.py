"""Identify GND stitch sites blocked only by movable inner/rear tracks."""
from pathlib import Path
from collections import defaultdict
import pcbnew as p
import json,math

HERE=Path(__file__).resolve().parent
b=p.LoadBoard(str(HERE/'ChryslerScanner_V240_SD.kicad_pcb'))
p.ZONE_FILLER(b).Fill(b.Zones())
mm=lambda n:round(n*1e6)
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
class Grid:
 def __init__(self):self.items=[];self.cells=defaultdict(set)
 def keys(self,box):
  return [(x,y) for x in range(math.floor(box.GetLeft()/2e6),math.floor(box.GetRight()/2e6)+1)
                for y in range(math.floor(box.GetTop()/2e6),math.floor(box.GetBottom()/2e6)+1)]
 def add(self,item,layer,shape):
  i=len(self.items);self.items.append((item,layer,shape))
  for key in self.keys(shape.BBox(mm(.7))):self.cells[key].add(i)
 def nearby(self,shape):
  ids=set()
  for key in self.keys(shape.BBox(mm(.7))):ids.update(self.cells.get(key,()))
  return [self.items[i] for i in ids]
copper,holes,apertures=Grid(),Grid(),Grid();padmap={}
for fp in b.GetFootprints():
 for q in fp.Pads():
  padmap[q.m_Uuid.AsString()]=q
  if q.HasDrilledHole():holes.add(q,None,q.GetEffectiveHoleShape())
  for layer in layers:
   if q.IsOnLayer(layer):
    shape=q.GetEffectiveShape(layer)
    if q.GetNetname()!='GND':copper.add(q,layer,shape)
    if q.GetAttribute()==p.PAD_ATTRIB_SMD:apertures.add(q,layer,shape)
for t in b.GetTracks():
 if t.GetClass()=='PCB_VIA':holes.add(t,None,t.GetEffectiveHoleShape())
 if t.GetNetname()!='GND':
  for layer in layers:
   if t.IsOnLayer(layer):copper.add(t,layer,t.GetEffectiveShape(layer))
outer=[z for z in b.Zones() if not z.GetIsRuleArea() and any(z.IsOnLayer(l) for l in (p.F_Cu,p.B_Cu))]
keep=[z for z in b.Zones() if z.GetIsRuleArea()]
collide=lambda a,z,c:p.SHAPE.Collide(a,z,mm(c))
targets={'C38.2':'47909c98-ed77-4328-a695-51a6878f8380','C57.2':'2fcc60b1-304c-4ecb-9d1d-b02adb7c047c',
 'C60.2':'d11fdab2-67db-4f0d-8b41-126e45e624d8','J4.SH':'408d8e6c-5702-4067-9d8f-5c4cf212c990'}
result={}
for label,key in targets.items():
 q=padmap[key];origin=q.GetPosition();layer=p.F_Cu if q.IsOnLayer(p.F_Cu) else p.B_Cu
 regions=[]
 for z in outer:
  if not z.IsOnLayer(layer):continue
  poly=z.GetFilledPolysList(layer)
  for i in range(poly.OutlineCount()):
   if poly.Contains(origin,i):regions.append((poly,i))
 options=[]
 offsets=[(ix,iy) for ix in range(-60,61) for iy in range(-60,61) if math.hypot(ix*.05,iy*.05)<=3.0]
 offsets.sort(key=lambda pair:pair[0]**2+pair[1]**2)
 for ix,iy in offsets:
  point=p.VECTOR2I(origin.x+mm(ix*.05),origin.y+mm(iy*.05));circle=p.SHAPE_CIRCLE(point,mm(.3))
  inside_island=any(poly.Contains(point,i) for poly,i in regions)
  if any(collide(circle,s,.2005) for _,_,s in holes.nearby(circle)):continue
  if any(item.m_Uuid.AsString()!=key and collide(circle,s,.10) for item,_,s in apertures.nearby(circle)):continue
  via_in_pad=any(item.m_Uuid.AsString()==key and collide(circle,s,.10) for item,_,s in apertures.nearby(circle))
  if any(z.GetDoNotAllowVias() and collide(circle,z.Outline(),.02) for z in keep):continue
  bad={}
  for item,l,s in copper.nearby(circle):
   if not collide(circle,s,.1505):continue
   bad[item.m_Uuid.AsString()]=(item,l)
  if len(bad)>3:continue
  if any(item.GetClass()!='PCB_TRACK' or item.IsLocked() for item,l in bad.values()):continue
  neck=None
  if not inside_island:
   segment=p.SHAPE_SEGMENT(origin,point,mm(.25))
   if any(l==layer and item.m_Uuid.AsString() not in bad and collide(segment,s,.155)
          for item,l,s in copper.nearby(segment)):continue
   if any(item.GetNetname()!='GND' and collide(segment,s,.205) for item,_,s in holes.nearby(segment)):continue
   neck={'layer':p.LayerName(layer),'widthMm':.25,
         'points':[[p.ToMM(origin.x),p.ToMM(origin.y)],[p.ToMM(point.x),p.ToMM(point.y)]]}
  options.append({'xy':[p.ToMM(point.x),p.ToMM(point.y)],'distanceMm':round(math.hypot(ix*.05,iy*.05),5),
   'requiresFilledCappedViaInOwnPad':via_in_pad,
   'groundNeck':neck,
   'blockingTracks':[{'uuid':uid,'net':item.GetNetname(),'layer':p.LayerName(l),'widthMm':p.ToMM(item.GetWidth()),
       'start':[p.ToMM(item.GetStart().x),p.ToMM(item.GetStart().y)],'end':[p.ToMM(item.GetEnd().x),p.ToMM(item.GetEnd().y)]}
       for uid,(item,l) in bad.items()]})
 options.sort(key=lambda item:(len(item['blockingTracks']),sum(t['layer']=='F.Cu' for t in item['blockingTracks']),
                              item['requiresFilledCappedViaInOwnPad'],item['distanceMm']))
 result[label]={'filledIslandRegions':len(regions),'options':options[:12]}
(HERE/'candidate-sites.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({key:{'regions':value['filledIslandRegions'],'optionCount':len(value['options']),
 'first':value['options'][:2]} for key,value in result.items()},indent=2))
