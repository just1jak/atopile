// SPDX-License-Identifier: GPL-3.0-only
import {PermissionsAndroid,Platform} from 'react-native';
import type {Transport} from '@chrysler/core';
export type Peripheral={id:string;name:string};
const SERVICE='6e400001-b5a3-f393-e0a9-e50e24dcca9e',RX='6e400002-b5a3-f393-e0a9-e50e24dcca9e',TX='6e400003-b5a3-f393-e0a9-e50e24dcca9e';
let initialized=false;
async function manager(){
  let manager:typeof import('react-native-ble-manager').default;
  try{manager=(await import('react-native-ble-manager')).default;}catch{throw new Error('BLE needs a development build. Expo Go supports recording import only.');}
  if(Platform.OS==='android'){
    const permissions=Number(Platform.Version)>=31?[PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT]:[PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
    const result=await PermissionsAndroid.requestMultiple(permissions);
    if(permissions.some(p=>result[p]!==PermissionsAndroid.RESULTS.GRANTED))throw new Error('Bluetooth permission is required to find your scanner.');
  }
  if(!initialized){await manager.start({showAlert:true});initialized=true;}
  return manager;
}
export async function scan(onFound:(p:Peripheral)=>void):Promise<void>{
  const ble=await manager();
  const listener=ble.onDiscoverPeripheral(p=>{
    const name=[p.name,p.advertising.localName].find(n=>n?.startsWith('Chrysler-RC-'));
    if(name)onFound({id:p.id,name});
  });
  try{await ble.scan({serviceUUIDs:[SERVICE],seconds:6,allowDuplicates:false});await new Promise(resolve=>setTimeout(resolve,6500));}
  finally{listener.remove();await ble.stopScan().catch(()=>{});}
}
async function bounded<T>(work:Promise<T>,ms:number,message:string,linkLoss?:Promise<never>):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  const deadline=new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(new Error(message)),ms);});
  try{return await Promise.race(linkLoss?[work,deadline,linkLoss]:[work,deadline]);}
  finally{clearTimeout(timer);}
}
export async function connect(id:string,receive:(bytes:Uint8Array)=>void,lost:(message:string)=>void):Promise<Transport>{
  const ble=await manager();
  let closing=false,ready=false;
  const matches=(peripheral:string)=>peripheral.toLowerCase()===id.toLowerCase();
  let notifications:ReturnType<typeof ble.onDidUpdateValueForCharacteristic>|undefined;
  let rejectSetup!:(error:Error)=>void;
  const linkLoss=new Promise<never>((_,reject)=>{rejectSetup=reject;});
  const disconnected=ble.onDisconnectPeripheral(e=>{
    if(!matches(e.peripheral)||closing)return;
    const message='Bluetooth disconnected. Board SD logging may still be running.';
    if(ready){lost(message);void close();}
    else rejectSetup(new Error(message));
  });
  const close=async()=>{
    if(closing)return;
    closing=true;
    notifications?.remove();
    disconnected.remove();
    await bounded(ble.disconnect(id),3000,'Bluetooth disconnect timed out').catch(()=>{});
  };
  try{
    await bounded(ble.connect(id),15000,'Scanner did not respond to Bluetooth connection. Move closer and try again.',linkLoss);
    await bounded(ble.retrieveServices(id),10000,'Could not discover scanner services',linkLoss);
    if(Platform.OS==='android')await bounded(ble.createBond(id),90000,'Bluetooth pairing timed out',linkLoss);
    // Encrypted/authenticated read triggers iOS pairing and verifies link security
    // before the protocol response timer starts. Passkey is shown over USB only.
    await bounded(ble.read(id,SERVICE,TX),90000,'Scanner authentication timed out',linkLoss);
    notifications=ble.onDidUpdateValueForCharacteristic(e=>{
      if(matches(e.peripheral)&&e.characteristic.toLowerCase()===TX)receive(Uint8Array.from(e.value));
    });
    await bounded(ble.startNotification(id,SERVICE,TX),10000,'Could not subscribe to scanner data',linkLoss);
    ready=true;
    return {kind:'ble',write:async bytes=>{
      if(closing)throw new Error('Bluetooth connection closed');
      await ble.write(id,SERVICE,RX,Array.from(bytes),20);
    },close};
  }catch(error){await close();throw error;}
}
