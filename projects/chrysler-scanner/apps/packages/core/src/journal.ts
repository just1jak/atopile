// SPDX-License-Identifier: GPL-3.0-only
import {MAX_WIRE,parse,decodeCapture,utf8,type Capture} from './protocol';
export function crc32(bytes:Uint8Array):number {let c=0xffffffff;for(const b of bytes){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^(0xedb88320&-(c&1));}return (c^0xffffffff)>>>0;}
export function journalRecord(type:number,sequence:number,us:number,payload:Uint8Array,lost=0,utc=0):Uint8Array {
  if(payload.length>MAX_WIRE)throw new Error('Journal payload too large');
  const out=new Uint8Array(40+payload.length),v=new DataView(out.buffer);
  out.set([67,66,82,49,type,utc?1:0,36,0]);v.setUint32(8,payload.length,true);v.setUint32(12,sequence,true);
  v.setBigUint64(16,BigInt(Math.floor(us)),true);v.setBigUint64(24,BigInt(Math.floor(utc)),true);v.setUint32(32,lost,true);
  out.set(payload,36);v.setUint32(out.length-4,crc32(out.subarray(0,-4)),true);return out;
}
export type JournalSummary={records:number;frames:number;skippedBytes:number;sequenceGaps:number;reportedLoss:number;cleanStop:boolean;events:string[]};
export class JournalReader {
  private buffer=new Uint8Array();private header=false;private expected=0;private lastClean=false;
  summary:JournalSummary={records:0,frames:0,skippedBytes:0,sequenceGaps:0,reportedLoss:0,cleanStop:false,events:[]};
  constructor(private sink:(capture:Capture)=>void){}
  feed(chunk:Uint8Array,final=false):void {
    const merged=new Uint8Array(this.buffer.length+chunk.length);merged.set(this.buffer);merged.set(chunk,this.buffer.length);
    let p=0;
    if(!this.header){if(merged.length<8){this.buffer=merged;return;}if(utf8(merged.subarray(0,8))!=='CBSDRAW1')throw new Error('Not a CBSDRAW1 recording');this.header=true;p=8;}
    while(p+40<=merged.length){
      const v=new DataView(merged.buffer,merged.byteOffset+p),n=v.getUint32(8,true),total=n+40;
      if(merged[p]!==67||merged[p+1]!==66||merged[p+2]!==82||merged[p+3]!==49||v.getUint16(6,true)!==36||n>MAX_WIRE){p++;this.summary.skippedBytes++;continue;}
      if(p+total>merged.length){if(!final)break;p++;this.summary.skippedBytes++;continue;}
      const record=merged.subarray(p,p+total);
      if(crc32(record.subarray(0,-4))!==v.getUint32(total-4,true)){p++;this.summary.skippedBytes++;continue;}
      const seq=v.getUint32(12,true);if(seq!==this.expected)this.summary.sequenceGaps++;this.expected=(seq+1)>>>0;
      this.summary.records++;this.summary.reportedLoss=Math.max(this.summary.reportedLoss,v.getUint32(32,true));this.lastClean=false;
      const payload=record.subarray(36,-4);
      if(record[4]===2){const f=parse(payload),c=f?decodeCapture(f,this.summary.frames+1):null;if(c){this.summary.frames++;this.sink(c);}}
      else if(record[4]===4){const event=utf8(payload);this.lastClean=event==='session_clean_stop';this.summary.events.push(event);if(this.summary.events.length>24)this.summary.events.shift();}
      p+=total;
    }
    this.buffer=merged.slice(p);
  }
  finish():JournalSummary {
    if(!this.header)throw new Error('Incomplete recording header');
    this.feed(new Uint8Array(),true);
    this.summary.skippedBytes+=this.buffer.length;this.buffer=new Uint8Array();
    this.summary.cleanStop=this.lastClean&&!this.summary.skippedBytes&&!this.summary.sequenceGaps;
    return {...this.summary,events:[...this.summary.events]};
  }
}
export const CSV_HEADER='scanner_ms,bus,obd_pin,baud,validated,hex,description\n';
export function csvRow(c:Capture):string {return [c.ms,c.bus,c.obdPin??'',c.baud??'',c.validated,c.hex,c.description].map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')+'\n';}
