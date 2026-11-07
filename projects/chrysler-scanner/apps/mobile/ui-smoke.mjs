import {_electron} from 'playwright';
import electron from 'electron';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,join,extname} from 'node:path';
const root=resolve('mobile/dist'),artifacts=resolve('artifacts');await mkdir(artifacts,{recursive:true});
const server=createServer(async(req,res)=>{
  const name=decodeURIComponent((req.url??'/').split('?')[0]);
  const file=resolve(root,'.'+(name==='/'?'/index.html':name));
  if(!file.startsWith(root+requireSeparator())&&file!==join(root,'index.html')){res.writeHead(403);res.end();return;}
  try{res.setHeader('Content-Type',extname(file)==='.js'?'application/javascript':extname(file)==='.html'?'text/html':'application/octet-stream');res.end(await readFile(file));}catch{res.writeHead(404);res.end();}
});
function requireSeparator(){return process.platform==='win32'?'\\':'/';}
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url=`http://127.0.0.1:${server.address().port}/`;
const main=join(artifacts,'mobile-preview-main.cjs');
await writeFile(main,`const {app,BrowserWindow}=require('electron');app.whenReady().then(()=>{const w=new BrowserWindow({show:false,width:430,height:932,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,offscreen:true,backgroundThrottling:false}});w.loadURL(${JSON.stringify(url)});});`);
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const app=await _electron.launch({executablePath:electron,args:[main,'--disable-gpu'],env,timeout:30000});
try{
  const page=await app.firstWindow();await page.getByText('Bus monitor',{exact:true}).waitFor();
  const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Open recording',exact:true}).click();
  await (await chooser).setFiles(join(artifacts,'SYNTHETIC-SAMPLE.cbr'));
  await page.getByText('6,000 frames',{exact:true}).waitFor();
  const png=await app.evaluate(async({BrowserWindow})=>(await BrowserWindow.getAllWindows()[0].webContents.capturePage(undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64'));
  await writeFile(join(artifacts,'mobile-recording-review.png'),Buffer.from(png,'base64'));
  console.log('PASS: React Native phone layout and real 6000-frame file import in web preview');
}finally{await app.close();await new Promise(resolve=>server.close(resolve));}
