// SPDX-License-Identifier: GPL-3.0-only
// Selected passive formulas ported from Laszlo Daniel's original CCD.cs/PCI.cs.
// Exact source locations and limits are in apps/SOURCES.md. No SCI inference.
import type {Capture,Metric} from './protocol';
export function decodeBroadcast(c:Capture,enabled=false):Capture {
  if(!enabled||!c.validated||c.bus==='SCI')return c;
  const m=c.bytes,pci=c.bus==='PCI',metrics:Metric[]=[];
  const add=(id:string,label:string,value:number,unit:string)=>metrics.push({id,label,value,unit});
  let description=c.description;
  if(pci&&m[0]===0x10&&m.length===7){
    description='Engine speed · vehicle speed · MAP';
    add('rpm','Engine speed',((m[1]<<8)|m[2])*.25,'rpm');
    add('speed','Vehicle speed',((m[3]<<8)|m[4])*.0049*1.609344,'km/h');
    add('map','Manifold pressure',m[5],'kPa');
  } else if(((pci&&m[0]===0xc0)||(!pci&&m[0]===0x0c))&&m.length===6){
    description='Battery · oil pressure · temperatures';
    add('battery','Battery voltage',m[1]*(pci?.0625:.125),'V');
    add('oil','Oil pressure',m[2]*.5*6.894757,'kPa');
    add('coolant','Coolant temperature',m[3]-(pci?40:64),'°C');
    add('ambient','Ambient temperature',m[4]-(pci?40:64),'°C');
  } else if(!pci&&m[0]===0x24&&m.length===4){description='Vehicle speed';add('speed','Vehicle speed',m[2],'km/h');}
  else if(!pci&&m[0]===0xe4&&m.length===4){
    description='Engine speed · MAP';add('rpm','Engine speed',m[1]*32,'rpm');add('map','Manifold pressure',m[2]*.1217*.4911542*6.894757,'kPa');
  }
  return {...c,description,metrics};
}
