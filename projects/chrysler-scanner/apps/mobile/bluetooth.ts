import type {Transport} from '@chrysler/core';
export type Peripheral={id:string;name:string};
export async function scan(_onFound:(p:Peripheral)=>void):Promise<void>{throw new Error('Live BLE uses an iOS/Android development build. Recording import works in this web preview.');}
export async function connect(_id:string,_receive:(bytes:Uint8Array)=>void,_lost:(message:string)=>void):Promise<Transport>{throw new Error('BLE is unavailable in web preview');}
