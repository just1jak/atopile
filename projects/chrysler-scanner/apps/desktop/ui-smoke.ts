import {_electron} from 'playwright';
import electron from 'electron';
import {resolve,join} from 'node:path';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {encode,checksum,crc8,journalRecord} from '@chrysler/core';
async function main(){
  const folder=resolve('artifacts');await mkdir(folder,{recursive:true});
  const records:Uint8Array[]=[new TextEncoder().encode('CBSDRAW1')];
  records.push(journalRecord(4,0,0,new TextEncoder().encode('SYNTHETIC UI TEST FIXTURE; not vehicle data')));
  for(let i=0;i<6000;i++){
    const sci=i%3===2,pci=i%3===1;
    const data=sci?Uint8Array.of(0x12,0x34,0x56):pci?Uint8Array.of(0x10,0x1f,0x40,0x10,0x20,93,0):Uint8Array.of(0xe4,48+i%8,85,0);
    if(!sci)data[data.length-1]=pci?crc8(data.subarray(0,-1)):checksum(data.subarray(0,-1));
    const payload=new Uint8Array(data.length+(sci?6:4));new DataView(payload.buffer).setUint32(0,i*20,false);if(sci)payload.set([15,3],4);payload.set(data,sci?6:4);
    records.push(journalRecord(2,i+1,i*20000,encode(sci?0xa7:pci?0xc7:0x97,sci?0x92:1,payload)));
  }
  records.push(journalRecord(4,6001,120000000,new TextEncoder().encode('session_clean_stop')));
  const file=join(folder,'SYNTHETIC-SAMPLE.cbr'),csv=join(folder,`export-${Date.now()}.csv`);
  await writeFile(file,Buffer.concat(records));
  const env={...process.env,CHRYSLER_TEST_HIDE:'1'};delete env.ELECTRON_RUN_AS_NODE;
  const app=await _electron.launch({executablePath:process.env.CHRYSLER_PACKAGED_EXE??electron as unknown as string,args:process.env.CHRYSLER_PACKAGED_EXE?['--disable-gpu']:[resolve('desktop'),'--disable-gpu'],env,timeout:30000});
  try {
    const page=await app.firstWindow(),errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await page.getByRole('heading',{name:'Live capture',exact:true}).waitFor();
    const ports=await page.evaluate(async()=>{const api=(window as any).scanner;if(!api)throw new Error('Preload bridge unavailable');return api.ports();});
    if(!Array.isArray(ports))throw new Error('Serial binding failed');
    await app.evaluate(({dialog},path)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[path]});},file);
    await page.getByRole('button',{name:'Open recording',exact:true}).click();
    await page.getByRole('heading',{name:'SYNTHETIC-SAMPLE.cbr',exact:true}).waitFor();
    await page.getByText('Historical Chrysler profile',{exact:true}).click();
    await page.locator('tbody tr').first().waitFor();
    if(await page.locator('tbody tr').count()!==500)throw new Error('Bounded table view failed');
    const capture=async(name:string)=>{
      await page.evaluate(()=>{window.scrollTo(0,0);return new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));});
      const png=await app.evaluate(async({BrowserWindow})=>{
        const window=BrowserWindow.getAllWindows()[0];
        return (await window.webContents.capturePage(undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
      });
      await writeFile(join(folder,name),Buffer.from(png,'base64'));
    };
    const lanes=await page.locator('.trace-row strong').allTextContents();
    if(lanes.length!==3||lanes.some(n=>Number(n)<1))throw new Error('Bus activity trace lost a populated channel');
    await capture('desktop-recording-review.png');
    await page.evaluate(()=>window.scrollTo(0,0));
    await capture('desktop-instrument-panel.png');
    await app.evaluate(({dialog},path)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath:path});},csv);
    await page.getByRole('button',{name:'Export all frames CSV',exact:true}).click();
    let content='';for(let i=0;i<100;i++){try{content=await readFile(csv,'utf8');if(content.split('\n').length>=6002)break;}catch{}await new Promise(r=>setTimeout(r,50));}
    if(content.split('\n').length!==6002)throw new Error('CSV export lost frames outside the retained preview');
    await page.getByRole('button',{name:'Live capture',exact:true}).click();
    await page.getByText('No input signal',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Recordings',exact:true}).click();
    await page.getByRole('heading',{name:'SYNTHETIC-SAMPLE.cbr',exact:true}).waitFor();
    await page.getByRole('button',{name:'Device & pairing'}).click();await page.getByRole('heading',{name:'Device & pairing',exact:true}).waitFor();
    await capture('desktop-device.png');
    if(errors.length)throw new Error(errors.join('\n'));
    console.log('PASS: native serial binding, secure preload, import 6000 frames, bounded view, original decoders, full CSV export, device UI');
  }finally{await app.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
