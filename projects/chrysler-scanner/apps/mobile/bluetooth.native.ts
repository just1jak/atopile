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
  const listener=ble.onDiscoverPeripheral(p=>{if(p.name?.startsWith('Chrysler-RC-'))onFound({id:p.id,name:p.name});});
  try{await ble.scan({serviceUUIDs:[SERVICE],seconds:6,allowDuplicates:false});await new Promise(resolve=>setTimeout(resolve,6500));}
  finally{listener.remove();await ble.stopScan().catch(()=>{});}
}
export async function connect(id:string,receive:(bytes:Uint8Array)=>void,lost:(message:string)=>void):Promise<Transport>{
  const ble=await manager();let closing=false;
  await ble.connect(id);
  let notifications:ReturnType<typeof ble.onDidUpdateValueForCharacteristic>|undefined;
  let disconnected:ReturnType<typeof ble.onDisconnectPeripheral>|undefined;
  try{
    await ble.retrieveServices(id);
    if(Platform.OS==='android')await ble.createBond(id);
    // Encrypted/authenticated read triggers iOS pairing and verifies link security
    // before the protocol response timer starts. Passkey is shown over USB only.
    await ble.read(id,SERVICE,TX);
    notifications=ble.onDidUpdateValueForCharacteristic(e=>{if(e.peripheral===id&&e.characteristic.toLowerCase()===TX)receive(Uint8Array.from(e.value));});
    disconnected=ble.onDisconnectPeripheral(e=>{if(e.peripheral===id&&!closing)lost('Bluetooth disconnected. Board SD logging may still be running.');});
    await ble.startNotification(id,SERVICE,TX);
    return {kind:'ble',write:bytes=>ble.write(id,SERVICE,RX,Array.from(bytes),20),close:async()=>{closing=true;notifications?.remove();disconnected?.remove();await ble.disconnect(id).catch(()=>{});}};
  }catch(error){notifications?.remove();disconnected?.remove();await ble.disconnect(id).catch(()=>{});throw error;}
}
