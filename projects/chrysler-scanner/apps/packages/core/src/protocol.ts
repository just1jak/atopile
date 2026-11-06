// SPDX-License-Identifier: GPL-3.0-only
// Original ChryslerScanner wire conventions; Rev C firmware protocol revision 2.
export const MAX_WIRE = 518;
export const BAUDS = [976,7812,62500,125000] as const;
export type Frame = { raw:Uint8Array; route:number; bus:number; command:number; mode:number; payload:Uint8Array };
export function checksum(p:Uint8Array):number { return p.reduce((s,b)=>(s+b)&255,0); }
export function be32(p:Uint8Array,offset=0):number { return new DataView(p.buffer,p.byteOffset+offset,4).getUint32(0,false); }
export function encode(route:number,mode:number,payload:Uint8Array=new Uint8Array()):Uint8Array {
  if(payload.length>512) throw new Error('Packet too large');
  const out=new Uint8Array(payload.length+6),n=payload.length+2;
  out.set([0x3d,n>>8,n&255,route,mode]); out.set(payload,5); out[out.length-1]=checksum(out.subarray(0,-1)); return out;
}
export function parse(raw:Uint8Array):Frame|null {
  if(raw.length<6||raw.length>MAX_WIRE||raw[0]!==0x3d||((raw[1]<<8)|raw[2])+4!==raw.length||checksum(raw.subarray(0,-1))!==raw[raw.length-1]) return null;
  return {raw:raw.slice(),route:raw[3],bus:(raw[3]>>4)&7,command:raw[3]&15,mode:raw[4],payload:raw.slice(5,-1)};
}
export class StreamParser {
  private pending:number[]=[]; private last=0; errors=0;
  reset():void { this.pending=[]; }
  expire(now:number):Frame[] {
    if(!this.pending.length||now-this.last<=100) return [];
    const out:Frame[]=[]; this.errors++;
    for(let i=1;i+6<=this.pending.length;) {
      const n=((this.pending[i+1]<<8)|this.pending[i+2])+4;
      const f=this.pending[i]===0x3d && i+n<=this.pending.length?parse(Uint8Array.from(this.pending.slice(i,i+n))):null;
      if(f){out.push(f);i+=n;}else i++;
    }
    this.reset(); return out;
  }
  feed(bytes:Uint8Array,now=Date.now()):Frame[] {
    const out=this.expire(now); if(bytes.length) this.last=now;
    for(const b of bytes) {
      this.pending.push(b);
      while(this.pending.length) {
        if(this.pending[0]!==0x3d){this.pending.shift();continue;}
        if(this.pending.length<3)break;
        const n=((this.pending[1]<<8)|this.pending[2])+4;
        if(n<6||n>MAX_WIRE){this.pending.shift();this.errors++;continue;}
        if(this.pending.length<n)break;
        const f=parse(Uint8Array.from(this.pending.slice(0,n)));
        if(!f){this.pending.shift();this.errors++;continue;}
        this.pending.splice(0,n);out.push(f);
      }
    }
    return out;
  }
}
// Commands are constructed by intent; there is no generic/raw-write app API.
export const requests={
  capabilities:()=>encode(4,0x7f),status:()=>encode(4,0x80),
  logging:(start:boolean)=>encode(4,0x81,Uint8Array.of(start?1:0)),
  sci:(route:number,speed:number)=>{
    if(!Number.isInteger(route)||route<0||route>2||!Number.isInteger(speed)||speed<0||speed>3)throw new Error('Invalid SCI selection');
    return encode(4,0x82,Uint8Array.of(route,speed));
  },lease:(acquire:boolean)=>encode(4,0x83,Uint8Array.of(acquire?1:0)),pairingCode:()=>encode(4,0x84)
};
export function utf8(bytes:Uint8Array):string {
  // TextDecoder is provided by Node, browsers and Expo's encoding runtime.
  return new TextDecoder('utf-8',{fatal:true}).decode(bytes);
}
function object(bytes:Uint8Array):Record<string,unknown> {
  const value:unknown=JSON.parse(utf8(bytes));
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('Malformed device JSON');
  return value as Record<string,unknown>;
}
export type Capabilities={fw:string;protocol:2|3;tx:false;programming:false;sd:boolean;ccd:boolean;pci:boolean;sci_raw:boolean;ble:boolean;can:boolean;lease?:boolean};
export function capabilities(frame:Frame):Capabilities {
  const v=object(frame.payload);
  if(frame.route!==0x85||frame.mode!==0x7f||![2,3].includes(v.protocol as number)||typeof v.fw!=='string'||!v.fw.startsWith('rev-c-passive-')||v.tx!==false||v.programming!==false||['sd','ccd','pci','sci_raw','ble','can'].some(k=>typeof v[k]!=='boolean'))throw new Error('Unsupported firmware. Install a Rev C passive protocol 2/3 image.');
  return v as Capabilities;
}
export type Status={ready:boolean;fault:boolean;logging:boolean;sdError:boolean;requested:boolean;sdBusy:boolean;sci:number;baud:number;rx:number[];lost:number[];reject:number;parse:number;owner:number;pairSeconds:number;bleLost:number};
export function status(frame:Frame):Status {
  if(frame.route!==0x85||frame.mode!==0x80)throw new Error('Unexpected status response');
  const v=object(frame.payload);
  for(const key of ['ready','fault','logging','sd_error','requested','sd_busy'])if(v[key]!==0&&v[key]!==1)throw new Error('Incomplete or invalid status');
  const uint=(n:unknown):n is number=>typeof n==='number'&&Number.isInteger(n)&&n>=0&&n<=0xffffffff;
  for(const [key,n] of [['rx',3],['lost',4]] as const)if(!Array.isArray(v[key])||(v[key] as unknown[]).length!==n||!(v[key] as unknown[]).every(uint))throw new Error('Invalid device counters');
  if(![0,16,32].includes(v.sci as number)||!BAUDS.includes(v.baud as typeof BAUDS[number])||!uint(v.reject)||!uint(v.parse))throw new Error('Invalid device status');
  if(v.owner!==undefined&&![0,1,2].includes(v.owner as number))throw new Error('Invalid control owner');
  if((v.pair_seconds!==undefined&&!uint(v.pair_seconds))||(v.ble_lost!==undefined&&!uint(v.ble_lost)))throw new Error('Invalid BLE status');
  return {ready:!!v.ready,fault:!!v.fault,logging:!!v.logging,sdError:!!v.sd_error,requested:!!v.requested,sdBusy:!!v.sd_busy,sci:v.sci as number,baud:v.baud as number,rx:v.rx as number[],lost:v.lost as number[],reject:v.reject,parse:v.parse,owner:(v.owner as number)??0,pairSeconds:(v.pair_seconds as number)??0,bleLost:(v.ble_lost as number)??0};
}
export type Capture={id:number;bus:'CCD'|'PCI'|'SCI';ms:number;hex:string;bytes:number[];validated:boolean;obdPin?:number;baud?:number;description:string;metrics:Metric[]};
export type Metric={id:string;label:string;value:number;unit:string};
export function crc8(p:Uint8Array):number {
  let c=255;for(const b of p){c^=b;for(let i=0;i<8;i++)c=((c<<1)^((c&128)?0x1d:0))&255;}return c^255;
}
export function decodeCapture(frame:Frame,id=0):Capture|null {
  if((frame.route&128)===0||frame.command!==7||![1,2,4].includes(frame.bus)||frame.payload.length<5)return null;
  let bytes=frame.payload.slice(4),obdPin:number|undefined,baud:number|undefined;
  if(frame.bus===2){
    if(frame.mode!==0x92||frame.payload.length<7||![7,15].includes(frame.payload[4])||frame.payload[5]>3)return null;
    obdPin=frame.payload[4];baud=BAUDS[frame.payload[5]];bytes=frame.payload.slice(6);
  } else if(frame.mode!==1 && (frame.mode&0x80)===0)return null;
  const valid=frame.bus!==2&&frame.mode===1&&bytes.length>=2&&(frame.bus===1?checksum(bytes.subarray(0,-1)):crc8(bytes.subarray(0,-1)))===bytes[bytes.length-1];
  const capture:Capture={id,bus:frame.bus===1?'CCD':frame.bus===4?'PCI':'SCI',ms:be32(frame.payload),hex:Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join(' ').toUpperCase(),bytes:Array.from(bytes),validated:valid,obdPin,baud,description:valid?'Unknown broadcast':frame.bus===2?'Raw SCI burst':'Raw / unverified',metrics:[]};
  return capture;
}
