"""Render actual PCB pads/courtyards and the planned four-layer roles."""
from pathlib import Path
import math,json
import sexpdata as sx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Circle,FancyBboxPatch
from matplotlib.transforms import Bbox
from pcb_geometry import courtyard,layer_outline,transform,board_mechanics
ROOT=Path(__file__).resolve().parents[1]
def name(e):return str(e[0]) if isinstance(e,list) and e else ''
def nodes(e,k):return [q for q in e if name(q)==k]
def one(e,k):return next((q for q in e if name(q)==k),None)
board=sx.loads((ROOT/'elec/layout/v240/v240.kicad_pcb').read_text())
placed=json.load(open(ROOT/'reference/v240-placement.json'))
plan=json.load(open(ROOT/'reference/layout-plan.json'))
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())
retained=json.load(open(ROOT/'reference/mechanical-anchors.json'))
board_width,board_height=board_mechanics()['size_mm']
colors={'Power supplies':'#8cc7ff','Bus interfaces':'#68ded6','Programming drivers':'#bda2ff','ESP32 / RF':'#a4df8f','ADC / control':'#eccf81','USB / reset':'#eda3c7','LED drivers':'#dfa467'}
def category(g):
 if g.startswith('power-') or g=='vehicle-input':return 'Power supplies'
 if g.startswith('sci-') or g in ['ccd','pci','obd-protection','obd']:return 'Bus interfaces'
 if g.startswith('program-'):return 'Programming drivers'
 if g=='mcu':return 'ESP32 / RF'
 if g in ['adc','control']:return 'ADC / control'
 if g=='usb':return 'USB / reset'
 return 'LED drivers'
fig=plt.figure(figsize=(18,12),facecolor='#10171e')
gs=fig.add_gridspec(2,1,height_ratios=[9,2],hspace=.21)
ax=fig.add_subplot(gs[0]);ax.set_facecolor('#10171e')
ax.set_xlim(-3,board_width+3);ax.set_ylim(board_height+3,-3);ax.set_aspect('equal')
fig.subplots_adjust(top=.91,bottom=.055,left=.06,right=.98)
fig.canvas.draw()
points_per_mm=(ax.transData.transform((1,0))[0]-ax.transData.transform((0,0))[0])*72/fig.dpi
ax.add_patch(FancyBboxPatch((0,0),board_width,board_height,boxstyle='round,pad=0,rounding_size=2',facecolor='#173e35',edgecolor='#82bfa2',linewidth=1.3))
for fp in nodes(board,'footprint'):
 ref=next(q[2] for q in nodes(fp,'property') if q[1]=='Reference');at=one(fp,'at');x,y=at[1]-100,at[2]-100;a=float(at[3]) if len(at)>3 else 0;t=math.radians(a)
 if ref in placed:
  p=placed[ref];color=colors[category(p['group'])]
  boundary=courtyard(fp).exterior;ax.plot(*boundary.xy,color=color,linewidth=.65 if ref in retained else .45,alpha=.95)
 # Show actual drawn body outlines, including C1's offset circular body.
 for layer in ['F.Fab','F.SilkS']:
  for geometry in layer_outline(fp,layer):
   geometry=transform(geometry,fp)
   geometries=list(geometry.geoms) if hasattr(geometry,'geoms') else [geometry]
   for line in geometries:ax.plot(*line.xy,color='#d5e4de',linewidth=.3,alpha=.75,zorder=3)
 for p in nodes(fp,'pad'):
  layers=one(p,'layers')[1:]
  if not any(str(q) in ['F.Cu','*.Cu'] for q in layers):continue
  px,py=one(p,'at')[1:3];w,h=one(p,'size')[1:3];xx=x+px*math.cos(t)+py*math.sin(t);yy=y-px*math.sin(t)+py*math.cos(t)
  if a in [90,270]:w,h=h,w
  if one(p,'drill'):
   drill=one(p,'drill')
   if str(drill[1])=='oval':
    dw,dh=map(float,drill[2:4])
    if a in [90,270]:dw,dh=dh,dw
    ax.add_patch(FancyBboxPatch((xx-w/2,yy-h/2),w,h,boxstyle=f'round,pad=0,rounding_size={min(w,h)/2}',facecolor='#c4ac72',linewidth=0))
    ax.add_patch(FancyBboxPatch((xx-dw/2,yy-dh/2),dw,dh,boxstyle=f'round,pad=0,rounding_size={min(dw,dh)/2}',facecolor='#10171e',linewidth=0))
   else:
    dia=float(drill[1]);ax.add_patch(Circle((xx,yy),max(w,h)/2,facecolor='#c4ac72',linewidth=0));ax.add_patch(Circle((xx,yy),dia/2,facecolor='#10171e',linewidth=0))
  else:ax.add_patch(Rectangle((xx-w/2,yy-h/2),w,h,facecolor='#c4ac72',linewidth=0,zorder=4))
 # Read the actual KiCad reference field. Never synthesize a center label
 # that could conceal missing/hidden designators in the deliverable.
 prop=next(q for q in nodes(fp,'property') if q[1]=='Reference')
 if one(prop,'layer')[1]=='F.SilkS' and not one(prop,'hide'):
  px,py=one(prop,'at')[1:3];xx=x+px*math.cos(t)+py*math.sin(t);yy=y-px*math.sin(t)+py*math.cos(t)
  font=one(one(prop,'effects'),'font');height=one(font,'size')[1];angle=one(prop,'at')[3]
  ax.text(xx,yy,prop[2],fontsize=height*points_per_mm,rotation=angle,color='#f3f6f4',ha='center',va='center',zorder=6)
x0,y0,x1,y1=plan['rf_keepout_mm']
ax.add_patch(Rectangle((x0,y0),x1-x0,y1-y0,fill=False,edgecolor='#d3a576',linestyle='--',linewidth=.8))
ax.text((x0+x1)/2,4.8,'Antenna keepout: all layers',color='#d3a576',fontsize=6,ha='center')
ax.set_xlim(-3,board_width+3);ax.set_ylim(board_height+3,-3);ax.set_aspect('equal');ax.set_xlabel('Millimeters from upper-left board corner',color='#a7b7b3');ax.tick_params(colors='#a7b7b3')
for sp in ax.spines.values():sp.set_color('#344841')
ax.set_title(f'ChryslerScanner {source.get("hardware_revision","V240")} · functional placement + four-layer PCB\n{len(source["parts"])} circuit parts · {len(plan["groups"])} circuit groups · {len(source["nets"])} nets · UNROUTED',loc='left',color='#ecf7f1',fontsize=16,pad=20)
ax2=fig.add_subplot(gs[1]);ax2.set_facecolor('#10171e');ax2.axis('off');ax2.set_xlim(0,100);ax2.set_ylim(0,5)
legend_x=0
for label,color in colors.items():
 ax2.add_patch(Rectangle((legend_x,4.4),.8,.25,facecolor=color,linewidth=0));ax2.text(legend_x+1.15,4.5,label,color='#dce8e3',fontsize=8,va='center');legend_x+=14.3
roles=[('L1 / F.Cu','Components, critical signals, local switching loops','#8cc7ff'),('L2 / In1.Cu','GND reference plane; no signal routing','#a4df8f'),('L3 / In2.Cu','Power distribution; GND beneath RF feed','#eccf81'),('L4 / B.Cu','Remaining signal routing','#bda2ff')]
for i,(layer,role,color) in enumerate(roles):
 yy=3.55-i*.75
 ax2.add_patch(Rectangle((0,yy-.23),11,.44,facecolor=color,edgecolor='none',alpha=.8))
 ax2.text(.5,yy,layer,color='#10171e',fontsize=9,va='center',weight='bold')
 ax2.text(12,yy,role,color='#dce8e3',fontsize=10,va='center')
ax2.text(61,3.6,f'{board_width} × {board_height} mm · expanded outline / mounting-hole spacing',color='#dce8e3',fontsize=9,va='center')
ax2.text(61,2.65,'Nominal 1.6 mm stackup; fabricator dimensions still pending.',color='#a7b7b3',fontsize=9,va='center')
ax2.text(61,1.7,'Ground zones defined, not filled. No tracks or vias.',color='#a7b7b3',fontsize=9,va='center')
ax2.text(61,.75,'Actual body outlines / reference fields shown; C1 body Ø8 mm.',color='#a7b7b3',fontsize=9,va='center')
fig.subplots_adjust(top=.91,bottom=.055,left=.06,right=.98)
out=ROOT/'renders';out.mkdir(exist_ok=True)
fig.savefig(out/'V240-placement-preview.png',dpi=190);fig.savefig(out/'V240-placement-preview.svg')
# A source-faithful close-up of the corrected capacitor and its neighbors.
fig.canvas.draw();lo=ax.transData.transform((4,board_height));hi=ax.transData.transform((32,26))
crop=Bbox.from_extents(lo[0],lo[1],hi[0],hi[1]).transformed(fig.dpi_scale_trans.inverted())
fig.savefig(out/'V240-C1-detail.png',dpi=240,bbox_inches=crop)
print('Rendered actual references / bodies, four-layer preview and C1 clearance detail')
