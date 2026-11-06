const {app,BrowserWindow}=require('electron');
const {readFileSync,writeFileSync}=require('node:fs');
const {join}=require('node:path');
app.whenReady().then(async()=>{
  try{
    const folder=join(__dirname,'../assets'),svg=readFileSync(join(folder,'icon.svg'),'utf8');
    const window=new BrowserWindow({show:false,webPreferences:{offscreen:true,nodeIntegration:false,contextIsolation:true,sandbox:true}});
    await window.loadURL('data:text/html,<html><body></body></html>');
    for(const size of [1024,256]){
      const data=await window.webContents.executeJavaScript(`(async()=>{const image=new Image();image.src=${JSON.stringify('data:image/svg+xml;base64,'+Buffer.from(svg).toString('base64'))};await image.decode();const canvas=document.createElement('canvas');canvas.width=canvas.height=${size};canvas.getContext('2d').drawImage(image,0,0,${size},${size});return canvas.toDataURL('image/png').split(',')[1];})()`);
      const png=Buffer.from(data,'base64');
      if(size===1024)writeFileSync(join(folder,'icon.png'),png);
      else {const header=Buffer.alloc(22);header.writeUInt16LE(1,2);header.writeUInt16LE(1,4);header.writeUInt16LE(1,10);header.writeUInt16LE(32,12);header.writeUInt32LE(png.length,14);header.writeUInt32LE(22,18);writeFileSync(join(folder,'icon.ico'),Buffer.concat([header,png]));}
    }
    console.log('Generated native app icons from source SVG');app.quit();
  }catch(error){console.error(error);app.exit(1);}
});
