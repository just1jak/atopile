import {describe,it,expect,vi} from 'vitest';
import {checksum,crc8,encode,parse,StreamParser,requests,decodeCapture,capabilities,status} from './protocol';
import {decodeBroadcast} from './decoders';
import {JournalReader,journalRecord,crc32} from './journal';
import {ScannerSession,type Transport} from './session';
const utf=(s:string)=>new TextEncoder().encode(s);
const response=(mode:number,p:unknown)=>encode(0x85,mode,p instanceof Uint8Array?p:utf(JSON.stringify(p)));
const cap={fw:'rev-c-passive-0.2.0',protocol:3,tx:false,programming:false,ble:true,can:false,sd:true,ccd:true,pci:true,sci_raw:true,lease:true};
const base={ready:1,fault:0,logging:0,sd_error:0,requested:0,sd_busy:0,sci:0,baud:7812,rx:[0,0,0],lost:[0,0,0,0],reject:0,parse:0,owner:1,pair_seconds:0,ble_lost:0};
function concat(...parts:Uint8Array[]):Uint8Array{const out=new Uint8Array(parts.reduce((n,p)=>n+p.length,0));let i=0;for(const p of parts){out.set(p,i);i+=p.length;}return out;}
function ccd():Uint8Array{const bytes=Uint8Array.of(0xe4,50,80,0);bytes[3]=checksum(bytes.subarray(0,-1));return encode(0x97,1,concat(new Uint8Array(4),bytes));}
describe('protocol and original decoder reuse',()=>{
  it('frames, fragments, rejects bad checksums and expires false long heads',()=>{
    const parser=new StreamParser(),packet=response(0x7f,cap),found=[];
    for(const b of packet)found.push(...parser.feed(Uint8Array.of(b),1));expect(found).toHaveLength(1);
    const bad=packet.slice();bad[5]^=1;expect(parser.feed(bad,2)).toEqual([]);
    parser.reset();expect(parser.feed(concat(Uint8Array.of(0x3d,1,250),packet),3)).toEqual([]);
    expect(parser.expire(104)).toHaveLength(1);expect(parser.errors).toBeGreaterThan(0);
  });
  it('strictly negotiates passive firmware and complete SD status',()=>{
    expect(capabilities(parse(response(0x7f,cap))!).protocol).toBe(3);
    expect(()=>capabilities(parse(response(0x7f,{...cap,tx:true}))!)).toThrow();
    expect(()=>status(parse(response(0x80,{...base,sd_busy:undefined}))!)).toThrow();
    expect(status(parse(response(0x80,base))!).sdBusy).toBe(false);
  });
  it('retains SCI source and only decodes checked known broadcasts',()=>{
    const sci=decodeCapture(parse(encode(0xa7,0x92,Uint8Array.of(0,0,0,1,15,3,0xbb)))!)!;
    expect(sci).toMatchObject({obdPin:15,baud:125000,validated:false,hex:'BB'});
    const c=decodeCapture(parse(ccd())!)!;expect(decodeBroadcast(c,true).metrics[0].value).toBe(1600);
    expect(decodeBroadcast(c,false).metrics).toEqual([]);
    const raw=ccd();raw[4]=0x82;raw[raw.length-1]=checksum(raw.subarray(0,-1));expect(decodeBroadcast(decodeCapture(parse(raw)!)!,true).metrics).toEqual([]);
    expect(crc8(utf('123456789'))).toBe(0x4b);
  });
  it('constructs only passive intent commands',()=>{
    for(const raw of [requests.capabilities(),requests.status(),requests.logging(true),requests.logging(false),requests.sci(2,3),requests.lease(false),requests.pairingCode()])expect(parse(raw)?.route).toBe(4);
    expect(()=>requests.sci(3,0)).toThrow();expect(()=>requests.sci(0,4)).toThrow();
  });
});
describe('streaming SD recovery',()=>{
  const rec=journalRecord(2,0,1000,ccd()),stop=journalRecord(4,1,2000,utf('session_clean_stop'));
  it('checks CRC reference and all split boundaries',()=>{
    expect(crc32(utf('123456789'))).toBe(0xcbf43926);
    const all=concat(utf('CBSDRAW1'),rec,stop);
    for(let cut=0;cut<=all.length;cut++){const frames:unknown[]=[];const r=new JournalReader(c=>frames.push(c));r.feed(all.slice(0,cut));r.feed(all.slice(cut));expect(r.finish().cleanStop).toBe(true);expect(frames).toHaveLength(1);}
  });
  it('never declares a torn record clean and recovers after plausible corrupt lengths',()=>{
    for(let cut=0;cut<stop.length;cut++){const r=new JournalReader(()=>{});r.feed(concat(utf('CBSDRAW1'),rec,stop.slice(0,cut)));expect(r.finish().cleanStop).toBe(false);}
    const corrupt=rec.slice();new DataView(corrupt.buffer).setUint32(8,500,true);
    const r=new JournalReader(()=>{});r.feed(concat(utf('CBSDRAW1'),corrupt,stop));const result=r.finish();expect(result.records).toBe(1);expect(result.cleanStop).toBe(false);expect(result.sequenceGaps).toBe(1);
  });
  it('recovers after malformed record payloads with valid outer CRCs',()=>{
    const invalidFrame=journalRecord(2,0,1000,Uint8Array.of(0));
    const invalidEvent=journalRecord(4,1,2000,Uint8Array.of(255));
    const reader=new JournalReader(()=>{});
    reader.feed(concat(utf('CBSDRAW1'),invalidFrame,invalidEvent,journalRecord(2,2,3000,ccd()),journalRecord(4,3,4000,utf('session_clean_stop'))));
    expect(reader.finish()).toMatchObject({frames:1,skippedBytes:invalidFrame.length+invalidEvent.length,cleanStop:false});
  });
});
describe('session confirmation and stale connection boundaries',()=>{
  it('waits through mounting/closing and invalidates eject confirmation on ownership loss',async()=>{
    const session=new ScannerSession();let stopped=false,queries=0,closed=false,owner=1;
    const transport:Transport={kind:'usb',close:async()=>{closed=true;},write:async bytes=>{
      const f=parse(bytes)!;let reply:Uint8Array;
      if(f.mode===0x7f)reply=response(f.mode,cap);
      else if(f.mode===0x81){stopped=true;reply=response(f.mode,Uint8Array.of(0));}
      else {queries++;reply=response(f.mode,{...base,owner,sd_busy:stopped&&queries<4?1:0});}
      queueMicrotask(()=>session.receive(reply));
    }};
    await session.connect(transport,'Test');await session.setLogging(false);
    expect(queries).toBeGreaterThanOrEqual(4);expect(session.state.safeToRemove).toBe(true);
    owner=0;await session.refresh();expect(session.state.safeToRemove).toBe(false);
    await session.disconnect();expect(closed).toBe(true);expect(session.state.status).toBeUndefined();
  });
  it('rejects stale ready state and a stop confirmation owned by another host',async()=>{
    const session=new ScannerSession();let owner=1;
    const transport:Transport={kind:'usb',close:async()=>{},write:async bytes=>{
      const f=parse(bytes)!;
      const reply=f.mode===0x7f?response(f.mode,cap):f.mode===0x81?response(f.mode,Uint8Array.of(0)):response(f.mode,{...base,owner});
      queueMicrotask(()=>session.receive(reply));
    }};
    await session.connect(transport,'Test');session.state.statusAt=Date.now()-4000;
    await expect(session.setLogging(true)).rejects.toThrow('not ready');
    owner=2;await expect(session.setLogging(false)).rejects.toThrow('ownership');
    expect(session.state.safeToRemove).toBe(false);await session.disconnect();
  });
  it('cannot publish SD stop confirmation after a disconnect during the status reply',async()=>{
    const session=new ScannerSession();let stopped=false;
    const transport:Transport={kind:'usb',close:async()=>{},write:async bytes=>{
      const request=parse(bytes)!;
      if(request.mode===0x81)stopped=true;
      const payload=request.mode===0x7f?cap:request.mode===0x81?Uint8Array.of(0):base;
      queueMicrotask(()=>session.receive(response(request.mode,payload)));
    }};
    await session.connect(transport,'Test');
    session.onState=state=>{
      if(stopped&&state.status)void session.disconnect();
    };
    await expect(session.setLogging(false)).rejects.toThrow('connection changed');
    expect(session.state).toMatchObject({phase:'disconnected',safeToRemove:false});
  });
  it('withdraws the previous stop confirmation on a malformed status',async()=>{
    const session=new ScannerSession();let invalid=false;
    const transport:Transport={kind:'usb',close:async()=>{},write:async bytes=>{
      const request=parse(bytes)!;
      const payload=request.mode===0x7f?cap:request.mode===0x81?Uint8Array.of(0):invalid?{}:base;
      queueMicrotask(()=>session.receive(response(request.mode,payload)));
    }};
    await session.connect(transport,'Test');await session.setLogging(false);
    expect(session.state.safeToRemove).toBe(true);
    invalid=true;
    await expect(session.refresh()).rejects.toThrow('invalid status');
    expect(session.state).toMatchObject({status:undefined,statusAt:0,safeToRemove:false});
  });
  it('rejects incompatible firmware and does not enable controls from arbitrary JSON',async()=>{
    const session=new ScannerSession();
    const transport:Transport={close:async()=>{},write:async()=>{queueMicrotask(()=>session.receive(response(0x7f,{...cap,protocol:99})));}};
    await expect(session.connect(transport,'Wrong')).rejects.toThrow();expect(session.state.phase).not.toBe('connected');
  });
});
