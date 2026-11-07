// SPDX-License-Identifier: GPL-3.0-only
import {app,BrowserWindow,ipcMain,dialog,type IpcMainInvokeEvent} from 'electron';
import {SerialPort} from 'serialport';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createReadStream,createWriteStream,type WriteStream} from 'node:fs';
import {stat} from 'node:fs/promises';
import {once} from 'node:events';
import {ScannerSession,JournalReader,journalRecord,csvRow,CSV_HEADER,type Capture,type Frame} from '@chrysler/core';
let window:BrowserWindow;
const session=new ScannerSession();
let currentImport:string|undefined,writer:WriteStream|undefined,writeSequence=0,recordingError='';
let activePort:SerialPort|undefined,computerStop:Promise<void>|undefined;
let batch:Capture[]=[],displayDropped=0,operation=false,computerPath='';
const send=(channel:string,data:unknown)=>{if(window&&!window.isDestroyed())window.webContents.send(channel,data);};
session.onState=state=>{
  if(state.phase==='error'&&writer){
    recordingError='USB disconnected. Computer journal is incomplete; board SD may still be recording.';
    void stopComputer(false).catch(()=>{});
  }
  send('scanner:state',state);
};
session.onCapture=(capture,frame)=>{
  if(batch.length<2000)batch.push(capture);else displayDropped++;
  if(writer){
    if(writer.writableLength>1024*1024){recordingError='Computer recording stopped: disk backlog. Recover the partial journal.';writer.destroy();writer=undefined;send('scanner:computer',{recording:false,path:computerPath,error:recordingError});}
    else writer.write(journalRecord(2,writeSequence++,performance.now()*1000,frame.raw));
  }
};
async function stopComputer(clean=true):Promise<void> {
  if(computerStop)return computerStop;
  const file=writer;writer=undefined;if(!file)return;
  const marker=clean?journalRecord(4,writeSequence++,performance.now()*1000,new TextEncoder().encode('session_clean_stop')):undefined;
  const path=computerPath;
  computerStop=(async()=>{
    const finished=once(file,'finish');
    file.end(marker);
    await finished;
  })();
  try {
    await computerStop;
  }finally{
    computerStop=undefined;
    send('scanner:computer',{recording:false,path,error:recordingError});
  }
}
function trusted(event:IpcMainInvokeEvent):void {
  const expected=pathToFileURL(join(__dirname,'renderer/index.html')).href;
  if(event.sender!==window.webContents||event.senderFrame!==window.webContents.mainFrame||event.senderFrame.url!==expected)throw new Error('Untrusted application context');
}
function handle(name:string,fn:(...args:any[])=>unknown):void {
  ipcMain.handle(name,async(event,...args)=>{trusted(event);return fn(...args);});
}
async function control(fn:()=>Promise<unknown>):Promise<unknown>{if(operation)throw new Error('Another operation is in progress');operation=true;try{return await fn();}finally{operation=false;}}
async function importFile(path:string):Promise<{frames:Capture[];summary:ReturnType<JournalReader['finish']>;name:string}> {
  const info=await stat(path);if(info.size>2*1024*1024*1024)throw new Error('Recording exceeds the 2 GiB import limit');
  const frames:Capture[]=[];const reader=new JournalReader(c=>{frames.push(c);if(frames.length>5000)frames.shift();});
  for await(const chunk of createReadStream(path,{highWaterMark:65536}))reader.feed(chunk as Buffer);
  return {frames,summary:reader.finish(),name:path.split(/[\\/]/).pop()??'Recording'};
}
app.whenReady().then(()=>{
  window=new BrowserWindow({show:process.env.CHRYSLER_TEST_HIDE!=='1',width:1440,height:980,minWidth:1040,minHeight:740,title:'Chrysler Scanner',backgroundColor:'#f5f7fa',webPreferences:{offscreen:process.env.CHRYSLER_TEST_HIDE==='1',backgroundThrottling:process.env.CHRYSLER_TEST_HIDE!=='1',preload:join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',event=>event.preventDefault());
  handle('scanner:ports',()=>SerialPort.list());
  handle('scanner:snapshot',()=>({...session.state}));
  handle('scanner:connect',(path:unknown)=>control(async()=>{
    if(typeof path!=='string'||!(await SerialPort.list()).some(p=>p.path===path))throw new Error('Choose an available serial port');
    await stopComputer();await session.disconnect();
    const port=new SerialPort({path,baudRate:250000,autoOpen:false,rtscts:false,hupcl:false});let closing=false;
    activePort=port;
    batch=[];displayDropped=0;
    const linkLost=(message:string)=>{
      if(!closing&&activePort===port){
        activePort=undefined;
        void session.disconnect(message);
      }
    };
    port.on('data',(data:Buffer)=>{if(activePort===port)session.receive(data);});
    port.on('error',error=>linkLost(error.message));
    port.on('close',()=>linkLost('USB disconnected. Board SD logging may still be running.'));
    try {
      await new Promise<void>((resolve,reject)=>port.open(error=>error?reject(error):resolve()));
      await new Promise<void>((resolve,reject)=>port.set({dtr:false,rts:false},error=>error?reject(error):resolve()));
      if(activePort!==port||!port.isOpen)throw new Error('USB disconnected during setup');
      await session.connect({kind:'usb',write:bytes=>new Promise((resolve,reject)=>port.write(bytes,error=>error?reject(error):resolve())),close:async()=>{
        closing=true;
        if(activePort===port)activePort=undefined;
        if(port.isOpen)await new Promise<void>(resolve=>port.close(()=>resolve()));
      }},path);
    }catch(error){closing=true;if(activePort===port)activePort=undefined;if(port.isOpen)port.close();throw error;}
  }));
  handle('scanner:disconnect',()=>control(async()=>{try{await stopComputer();}finally{await session.disconnect();}}));
  handle('scanner:logging',(start:unknown)=>control(()=>{if(typeof start!=='boolean')throw new Error('Invalid logging request');return session.setLogging(start);}));
  handle('scanner:sci',(route:unknown,speed:unknown)=>control(()=>session.setSci(Number(route),Number(speed))));
  handle('scanner:release',()=>control(()=>session.releaseControl()));
  handle('scanner:pairing',()=>control(()=>session.pairingCode()));
  handle('scanner:computer-start',()=>control(async()=>{
    const port=activePort;
    const sameConnection=()=>!!port&&activePort===port&&session.state.phase==='connected';
    if(!sameConnection())throw new Error('Connect the scanner first');
    if(writer||computerStop)throw new Error('Computer recording is already running or finishing');
    const result=await dialog.showSaveDialog(window,{title:'Record USB capture',defaultPath:`scanner-${new Date().toISOString().replaceAll(':','-')}.cbr`,filters:[{name:'Scanner journal',extensions:['cbr']}]});
    if(result.canceled||!result.filePath)return;
    if(!sameConnection())throw new Error('USB disconnected before recording began');
    const file=createWriteStream(result.filePath,{flags:'wx'});computerPath=result.filePath;recordingError='';writeSequence=0;
    file.on('error',error=>{if(writer&&writer!==file)return;if(writer===file)writer=undefined;recordingError=error.message;send('scanner:computer',{recording:false,path:result.filePath,error:error.message});});
    await once(file,'open');
    if(!sameConnection()){
      file.end('CBSDRAW1'); // Retain an explicitly incomplete journal if the file was already created.
      throw new Error('USB disconnected before recording began');
    }
    file.write('CBSDRAW1');
    file.write(journalRecord(4,writeSequence++,performance.now()*1000,new TextEncoder().encode(`Desktop USB capture; ${session.state.capabilities?.fw}; host UTC ${new Date().toISOString()}`)));
    writer=file;send('scanner:computer',{recording:true,path:computerPath,error:''});
  }));
  handle('scanner:computer-stop',()=>control(stopComputer));
  handle('scanner:import',()=>control(async()=>{
    const result=await dialog.showOpenDialog(window,{properties:['openFile'],filters:[{name:'Scanner journal',extensions:['cbr']}]});
    if(result.canceled)return null;
    const imported=await importFile(result.filePaths[0]);currentImport=result.filePaths[0];return imported;
  }));
  handle('scanner:export',()=>control(async()=>{
    if(!currentImport)throw new Error('Import a recording first');
    const result=await dialog.showSaveDialog(window,{defaultPath:'scanner-capture.csv',filters:[{name:'CSV',extensions:['csv']}]});
    if(result.canceled||!result.filePath)return;
    if(result.filePath===currentImport)throw new Error('Export must not overwrite the original recording');
    const output=createWriteStream(result.filePath,{flags:'wx'});let failure:Error|undefined;output.on('error',e=>{failure=e;});await once(output,'open');
    output.write(CSV_HEADER);let rows:string[]=[];
    const reader=new JournalReader(c=>rows.push(csvRow(c)));
    try {
      for await(const chunk of createReadStream(currentImport,{highWaterMark:65536})){
        reader.feed(chunk as Buffer);if(failure)throw failure;
        if(!output.write(rows.join('')))await once(output,'drain');rows=[];
      }
      reader.finish();output.end();await once(output,'finish');
    }catch(error){output.destroy();throw error;}
  }));
  const tick=setInterval(()=>{
    session.expire();if(batch.length){send('scanner:captures',{frames:batch,displayDropped});batch=[];}
  },100);
  let poll=false;const statusPoll=setInterval(()=>{if(session.state.phase==='connected'&&!operation&&!poll){poll=true;session.refresh().catch(()=>{}).finally(()=>{poll=false;});}},1000);
  let closing=false;
  window.on('close',event=>{
    if(!writer&&!computerStop)return;
    event.preventDefault();
    if(!closing){
      closing=true;
      stopComputer().catch(()=>{}).finally(()=>window.close());
    }
  });
  window.on('closed',()=>{clearInterval(tick);clearInterval(statusPoll);void session.disconnect();if(writer)writer.destroy();});
  void window.loadFile(join(__dirname,'renderer/index.html'));
});
app.on('window-all-closed',()=>app.quit());
