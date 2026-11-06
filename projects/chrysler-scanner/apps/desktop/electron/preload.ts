// SPDX-License-Identifier: GPL-3.0-only
import {contextBridge,ipcRenderer} from 'electron';
const on=(name:string,callback:(data:any)=>void)=>{const listener=(_:unknown,data:unknown)=>callback(data);ipcRenderer.on(name,listener);return()=>ipcRenderer.removeListener(name,listener);};
contextBridge.exposeInMainWorld('scanner',{
  ports:()=>ipcRenderer.invoke('scanner:ports'),snapshot:()=>ipcRenderer.invoke('scanner:snapshot'),
  connect:(path:string)=>ipcRenderer.invoke('scanner:connect',path),disconnect:()=>ipcRenderer.invoke('scanner:disconnect'),
  logging:(start:boolean)=>ipcRenderer.invoke('scanner:logging',start),sci:(route:number,speed:number)=>ipcRenderer.invoke('scanner:sci',route,speed),
  release:()=>ipcRenderer.invoke('scanner:release'),pairing:()=>ipcRenderer.invoke('scanner:pairing'),
  recordComputer:()=>ipcRenderer.invoke('scanner:computer-start'),stopComputer:()=>ipcRenderer.invoke('scanner:computer-stop'),
  importFile:()=>ipcRenderer.invoke('scanner:import'),exportCsv:()=>ipcRenderer.invoke('scanner:export'),
  onState:(cb:(d:any)=>void)=>on('scanner:state',cb),onCaptures:(cb:(d:any)=>void)=>on('scanner:captures',cb),onComputer:(cb:(d:any)=>void)=>on('scanner:computer',cb)
});
