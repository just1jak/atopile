"""Show native KiCad before/after renders and measured placement distances."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/'reference/placement-pass-1-candidate.json').read_text())
fig=plt.figure(figsize=(17,12),facecolor='#f4f5f7')
grid=fig.add_gridspec(2,2,height_ratios=[1.25,1],hspace=.12,wspace=.08)
for i,(filename,title) in enumerate([('V240-placement-pass-1-before.png','Before'),('V240-3D-top.png','First placement pass')]):
    ax=fig.add_subplot(grid[0,i]);ax.imshow(mpimg.imread(ROOT/'renders'/filename));ax.set_xlim(200,1230);ax.set_ylim(705,230);ax.axis('off');ax.set_title(title,fontsize=16,pad=10)
before=data['before']['critical_links'];after=data['after']['critical_links']
keys=[('R2','U2','Regulator feedback'),('R8','U5','Regulator feedback'),('C2','U1','USB switch input capacitor'),('C35','U12','USB bridge bulk bypass'),('R22','U10','RF matching proximity'),('C16','U6','VBB input capacitor')]
def distance(items,key):return next(q['distance_mm'] for q in items if (q['part'],q['anchor'],q['kind'])==key)
old=np.array([distance(before,k) for k in keys]);new=np.array([distance(after,k) for k in keys]);y=np.arange(len(keys))
ax=fig.add_subplot(grid[1,0]);ax.set_facecolor('#f4f5f7')
ax.barh(y+.18,old,height=.32,color='#a9b2c2',label='Before');ax.barh(y-.18,new,height=.32,color='#247a63',label='After')
ax.set_yticks(y,[f'{r} - {a}\n{kind}' for r,a,kind in keys]);ax.invert_yaxis();ax.set_xlim(0,max(old)*1.16);ax.set_xlabel('Pad-center distance (mm)');ax.set_title('Selected local connections',loc='left',fontsize=14,pad=12);ax.legend(frameon=False,loc='upper right',bbox_to_anchor=(1,1.15),ncol=2);ax.spines[['top','right']].set_visible(False)
for i,(a,b) in enumerate(zip(old,new)):
    ax.text(a+.2,i+.18,f'{a:.2f}',va='center',fontsize=9);ax.text(b+.2,i-.18,f'{b:.2f}',va='center',fontsize=9)
ax=fig.add_subplot(grid[1,1]);ax.axis('off')
old_span=data['before']['local_signal_half_perimeter_sum_mm'];new_span=data['after']['local_signal_half_perimeter_sum_mm']
summary=[f"{len(data['moved_references'])} footprints repositioned",f'{100*(old_span-new_span)/old_span:.1f}% less local signal net span',f'{old_span:.2f} -> {new_span:.2f} mm half-perimeter sum','',
    'Board: 110 x 55 mm, four copper layers','Connector, hole, LED, button, ESP32 and antenna positions retained','Circuit, package pads, paste geometry and BOM unchanged','245 visible references checked at 1.0 mm height / 0.15 mm stroke','',
    'Placement proxies, not routed trace lengths or performance results.','Power-loop placement targets remain in the review report.','U3/U4/U8 pin 5 requires electrical review (DRV GND versus NC).','Board remains unrouted; no tracks or vias added.']
for i,line in enumerate(summary):ax.text(.02,.96-i*.067,line,transform=ax.transAxes,fontsize=12 if i<3 else 10.5,weight='bold' if i<2 else 'normal',color='#172a33',va='top')
fig.suptitle('ChryslerScanner V240 - first placement pass',x=.04,ha='left',fontsize=22,weight='bold')
fig.subplots_adjust(top=.92,bottom=.055,left=.15,right=.98,wspace=.16)
fig.savefig(ROOT/'renders/V240-placement-pass-1-review.png',dpi=180)
print('Rendered native board comparison and pad-distance review')
