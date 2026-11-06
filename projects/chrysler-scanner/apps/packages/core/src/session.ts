// SPDX-License-Identifier: GPL-3.0-only
import {StreamParser,capabilities,status,requests,type Capabilities,type Status,type Frame,type Capture,decodeCapture} from './protocol';
export interface Transport {kind?:'usb'|'ble';write(bytes:Uint8Array):Promise<void>;close():Promise<void>;}
export type ConnectionState={phase:'disconnected'|'connecting'|'connected'|'incompatible'|'error';name:string;capabilities?:Capabilities;status?:Status;statusAt:number;safeToRemove:boolean;error?:string;parserErrors:number;};
type Waiter={mode:number;resolve:(f:Frame)=>void;reject:(e:Error)=>void;timer:ReturnType<typeof setTimeout>};
export class ScannerSession {
  private transport?:Transport;private parser=new StreamParser();private waiter?:Waiter;
  private serial:Promise<unknown>=Promise.resolve();private generation=0;private sequence=0;
  state:ConnectionState={phase:'disconnected',name:'',statusAt:0,safeToRemove:false,parserErrors:0};
  onState:(state:ConnectionState)=>void=()=>{};onCapture:(capture:Capture,frame:Frame)=>void=()=>{};
  private update(patch:Partial<ConnectionState>):void {this.state={...this.state,...patch};this.onState({...this.state});}
  private async request(mode:number,bytes:Uint8Array):Promise<Frame> {
    const generation=this.generation;
    const operation=async()=>{
      if(!this.transport||generation!==this.generation)throw new Error('Connection closed');
      return new Promise<Frame>((resolve,reject)=>{
        const timer=setTimeout(()=>{if(this.waiter?.timer===timer){this.waiter=undefined;reject(new Error('Scanner response timed out'));void this.disconnect('Scanner response timed out');}},3000);
        this.waiter={mode,resolve,reject,timer};
        this.transport!.write(bytes).catch(error=>{if(this.waiter?.timer===timer){clearTimeout(timer);this.waiter=undefined;reject(error);void this.disconnect(String(error));}});
      });
    };
    const result=this.serial.then(operation);this.serial=result.catch(()=>{});return result;
  }
  receive(bytes:Uint8Array,now=Date.now()):void {
    if(!this.transport)return;
    for(const f of this.parser.feed(bytes,now))this.handle(f);
    if(this.state.parserErrors!==this.parser.errors)this.update({parserErrors:this.parser.errors});
  }
  expire(now=Date.now()):void {for(const f of this.parser.expire(now))this.handle(f);}
  private handle(f:Frame):void {
    const capture=decodeCapture(f,++this.sequence);
    if(capture){if(this.state.capabilities)this.onCapture(capture,f);return;}
    const w=this.waiter;
    if(!w)return;
    if(f.route===0x8f){clearTimeout(w.timer);this.waiter=undefined;w.reject(new Error(`Scanner rejected command (0x${f.mode.toString(16)})`));}
    else if(f.route===0x85&&f.mode===w.mode){clearTimeout(w.timer);this.waiter=undefined;w.resolve(f);}
  }
  async connect(transport:Transport,name:string):Promise<void> {
    await this.disconnect();this.transport=transport;this.parser=new StreamParser();this.serial=Promise.resolve();this.sequence=0;
    this.update({phase:'connecting',name,error:undefined,status:undefined,capabilities:undefined,statusAt:0,safeToRemove:false,parserErrors:0});
    try {
      const cap=capabilities(await this.request(0x7f,requests.capabilities()));
      this.update({capabilities:cap});await this.refresh();this.update({phase:'connected'});
    }catch(error){await this.disconnect(String(error));throw error;}
  }
  async refresh():Promise<Status> {
    const value=status(await this.request(0x80,requests.status()));
    const owns=this.state.capabilities?.protocol!==3||value.owner===(this.transport?.kind==='ble'?2:1);
    this.update({status:value,statusAt:Date.now(),safeToRemove:this.state.safeToRemove&&owns&&!value.sdBusy&&!value.logging&&!value.requested&&!value.sdError});return value;
  }
  private requireReady():void {if(this.state.phase!=='connected'||Date.now()-this.state.statusAt>3500||!this.state.status?.ready||this.state.status.fault)throw new Error('Scanner is not ready');}
  async setLogging(start:boolean):Promise<void> {
    if(start){this.requireReady();if(!this.state.capabilities?.sd)throw new Error('SD logging is unavailable');}
    else if(this.state.phase!=='connected')throw new Error('Scanner is disconnected');
    this.update({safeToRemove:false});
    const ack=await this.request(0x81,requests.logging(start));
    if(ack.payload.length!==1||ack.payload[0]!==Number(start))throw new Error('Invalid logging acknowledgement');
    const generation=this.generation,deadline=Date.now()+10000;
    while(Date.now()<deadline) {
      if(generation!==this.generation)throw new Error('Connection changed during logging command');
      const s=await this.refresh();
      if(s.sdError)throw new Error('microSD error. Inspect or recover the recording.');
      if(start&&s.logging&&s.requested)return;
      if(!start&&!s.logging&&!s.sdBusy&&!s.requested){
        if(this.state.capabilities?.protocol===3&&s.owner!==(this.transport?.kind==='ble'?2:1))throw new Error('Control ownership changed. Stop again before removing the card.');this.update({safeToRemove:true});return;}
      if(start&&(s.fault||!s.requested))throw new Error('Recording did not start. Check the card and scanner status.');
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    throw new Error(start?'Recording start was not confirmed':'Stop not complete. Keep the card inserted.');
  }
  async setSci(route:number,speed:number):Promise<void> {
    this.requireReady();await this.request(0x82,requests.sci(route,speed));
    const rates=[976,7812,62500,125000],mask=[0,16,32];
    for(let i=0;i<20;i++){const s=await this.refresh();if(s.sci===mask[route]&&s.baud===rates[speed])return;await new Promise(r=>setTimeout(r,100));}
    throw new Error('SCI selection was not confirmed');
  }
  async releaseControl():Promise<void> {
    if(!this.state.capabilities?.lease)return;
    this.update({safeToRemove:false});await this.request(0x83,requests.lease(false));await this.refresh();
  }
  async pairingCode():Promise<{passkey:string;seconds:number}> {
    if(this.state.phase!=='connected'||this.state.capabilities?.protocol!==3)throw new Error('BLE pairing requires firmware 0.2.0');
    const f=await this.request(0x84,requests.pairingCode());
    const p=JSON.parse(new TextDecoder().decode(f.payload));
    if(!/^\d{6}$/.test(p.passkey)||!Number.isInteger(p.seconds)||p.seconds<1)throw new Error('Pairing window is closed');return p;
  }
  async disconnect(error?:string):Promise<void> {
    this.generation++;const transport=this.transport;this.transport=undefined;
    if(this.waiter){clearTimeout(this.waiter.timer);this.waiter.reject(new Error(error??'Disconnected'));this.waiter=undefined;}
    this.parser.reset();this.update({phase:error?'error':'disconnected',status:undefined,capabilities:undefined,statusAt:0,safeToRemove:false,error});
    if(transport)await transport.close().catch(()=>{});
  }
}
