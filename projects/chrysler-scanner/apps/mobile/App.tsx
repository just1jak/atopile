// SPDX-License-Identifier: GPL-3.0-only
import React,{useEffect,useMemo,useRef,useState} from 'react';
import {View,Text,Pressable,Image,StyleSheet,FlatList,Switch,AppState,Platform} from 'react-native';
import {SafeAreaProvider,SafeAreaView} from 'react-native-safe-area-context';
import {StatusBar} from 'expo-status-bar';
import * as DocumentPicker from 'expo-document-picker';
import {File as NativeFile,FileMode,Paths} from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import {ScannerSession,JournalReader,decodeBroadcast,CSV_HEADER,csvRow,type Capture,type ConnectionState,type JournalSummary} from '@chrysler/core';
import * as Bluetooth from './bluetooth';
const initial:ConnectionState={phase:'disconnected',name:'',statusAt:0,safeToRemove:false,parserErrors:0};
export default function App(){return <SafeAreaProvider><Workspace/></SafeAreaProvider>;}
function Workspace(){
  const session=useRef(new ScannerSession()).current;
  const list=useRef<FlatList<Capture>>(null);
  const [state,setState]=useState(initial),[frames,setFrames]=useState<Capture[]>([]),[tab,setTab]=useState('Capture'),[profile,setProfile]=useState(false),[devices,setDevices]=useState<Bluetooth.Peripheral[]>([]);
  const [busy,setBusy]=useState(''),[error,setError]=useState(''),[clock,setClock]=useState(Date.now()),[summary,setSummary]=useState<JournalSummary|null>(null),[fileName,setFileName]=useState(''),[route,setRoute]=useState(0),[speed,setSpeed]=useState(1);
  const pending=useRef<Capture[]>([]),fileSource=useRef<{uri:string;webFile?:globalThis.File}|null>(null);
  const operation=useRef(false);
  const run=async(label:string,fn:()=>Promise<unknown>)=>{
    if(operation.current)return;
    operation.current=true;
    setBusy(label);
    setError('');
    try{await fn();}
    catch(e){setError(String(e).replace(/^Error: /,''));}
    finally{operation.current=false;setBusy('');}
  };
  useEffect(()=>{
    session.onState=setState;session.onCapture=c=>{if(pending.current.length<1000)pending.current.push(c);};
    let polling=false;
    const timer=setInterval(()=>{
      setClock(Date.now());session.expire();
      if(pending.current.length&&!fileSource.current){const batch=pending.current;pending.current=[];setFrames(old=>[...old,...batch].slice(-1000));}else if(fileSource.current)pending.current=[];
      if(AppState.currentState==='active'&&session.state.phase==='connected'&&!polling){polling=true;session.refresh().catch(()=>{}).finally(()=>{polling=false;});}
    },1000);
    return()=>{clearInterval(timer);void session.disconnect();};
  },[]);
  useEffect(()=>{requestAnimationFrame(()=>list.current?.scrollToOffset({offset:0,animated:false}));},[tab,fileName]);
  const fresh=state.phase==='connected'&&clock-state.statusAt<3500,ready=fresh&&state.status?.ready&&!state.status.fault;
  const captures=useMemo(()=>frames.map(c=>decodeBroadcast(c,profile)),[frames,profile]);
  const metrics=useMemo(()=>{const map=new Map<string,{label:string;value:number;unit:string}>();for(const c of captures.slice(-100))for(const m of c.metrics)map.set(m.id,m);return [...map.values()].slice(0,4);},[captures]);
  async function chunks(source:{uri:string;webFile?:globalThis.File},sink:(bytes:Uint8Array)=>Promise<void>|void){
    if(Platform.OS==='web'&&source.webFile){for(let p=0;p<source.webFile.size;p+=65536)await sink(new Uint8Array(await source.webFile.slice(p,p+65536).arrayBuffer()));return;}
    const handle=new NativeFile(source.uri).open(FileMode.ReadOnly);
    try{for(;;){const bytes=await handle.readBytes(65536);if(!bytes.length)break;await sink(bytes);}}finally{handle.close();}
  }
  const importFile=()=>run('Opening recording',async()=>{
    const result=await DocumentPicker.getDocumentAsync({type:'*/*',copyToCacheDirectory:true,multiple:false});if(result.canceled)return;
    const asset=result.assets[0];if((asset.size??0)>70*1024*1024)throw new Error('Open one scanner segment at a time (maximum 70 MiB).');
    const source={uri:asset.uri,webFile:asset.file},view:Capture[]=[];
    const reader=new JournalReader(c=>{view.push(c);if(view.length>1000)view.shift();});
    await chunks(source,bytes=>{reader.feed(bytes);});const complete=reader.finish();
    fileSource.current=source;setSummary(complete);setFrames(view);setFileName(asset.name);setTab('Recordings');
  });
  const exportFile=()=>run('Exporting CSV',async()=>{
    const source=fileSource.current;if(!source)throw new Error('Open a recording first');
    if(Platform.OS==='web'){
      const parts=[CSV_HEADER];const reader=new JournalReader(c=>parts.push(csvRow(c)));await chunks(source,b=>reader.feed(b));reader.finish();
      const url=URL.createObjectURL(new Blob(parts,{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download='scanner.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);return;
    }
    const file=new NativeFile(Paths.cache,`scanner-${Date.now()}.csv`);file.create();const out=file.open(FileMode.WriteOnly);const encoder=new TextEncoder();
    try{await out.writeBytes(encoder.encode(CSV_HEADER));let rows:string[]=[];const reader=new JournalReader(c=>rows.push(csvRow(c)));await chunks(source,async bytes=>{reader.feed(bytes);await out.writeBytes(encoder.encode(rows.join('')));rows=[];});reader.finish();}finally{out.close();}
    if(!await Sharing.isAvailableAsync())throw new Error('File sharing is unavailable on this device');await Sharing.shareAsync(file.uri,{mimeType:'text/csv'});
  });
  return <SafeAreaView style={s.safe}><StatusBar style="dark"/><View style={s.header}><Image accessibilityIgnoresInvertColors style={s.logo} source={require('../assets/icon.png')}/><View><Text style={s.brand}>Chrysler Scanner</Text><Text style={s.subtitle}>Rev C scanner</Text></View><View style={[s.badge,fresh&&s.green]}><Text style={s.badgeText}>{fresh?'Connected':Platform.OS==='web'?'Web preview':'Offline'}</Text></View></View><View style={s.navigation}><View style={s.tabs}>{['Capture','Recordings','Device'].map(name=><Pressable accessibilityRole="tab" accessibilityState={{selected:tab===name}} key={name} onPress={()=>setTab(name)} style={[s.tab,tab===name&&s.tabActive]}><Text style={[s.tabText,tab===name&&s.tabTextActive]}>{name}</Text></Pressable>)}</View></View>
  {!!error&&<View style={s.error}><Text style={s.errorText}>{error}</Text></View>}
  <FlatList ref={list} data={tab==='Device'?[]:captures.slice(-300).reverse()} keyExtractor={c=>String(c.id)} contentContainerStyle={s.content} ListHeaderComponent={<View>
    <Text style={s.title}>{tab==='Capture'?'Bus monitor':tab==='Recordings'?'Recording review':'Connect your scanner'}</Text><Text style={s.copy}>{tab==='Device'?'Pair over a secure BLE link. The scanner can continue recording to microSD after you disconnect.':fileSource.current?fileName:Platform.OS==='web'?'Review saved scanner traffic on this PC.':'Receive CCD, PCI VPW and raw SCI traffic over Bluetooth.'}</Text>
    {tab!=='Device'&&<BusActivity frames={captures} imported={!!summary}/>}
    {tab!=='Device'&&!summary&&<View style={s.actions}>
      <Button title="Open recording" onPress={importFile} disabled={!!busy}/>
      {Platform.OS!=='web'&&!fresh&&<Button title="Connect scanner" secondary onPress={()=>setTab('Device')}/>}
    </View>}
    {tab==='Device'?<><View style={s.card}><Text style={s.section}>Bluetooth</Text><Text style={s.cardTitle}>Pair with Rev C</Text>{Platform.OS==='web'&&<Text style={s.detail}>Live Bluetooth is available in the native phone app.</Text>}<Text style={s.copy}>On desktop USB, open Device & pairing. Stop recording, hold the logger button for 3 seconds and show its pairing code. Enter it in your phone’s system dialog, then reboot the scanner and reconnect to resume capture.</Text><Button title={busy==='Scanning'?'Finding scanners…':'Find nearby scanners'} disabled={Platform.OS==='web'||!!busy||state.phase==='connected'} onPress={()=>run('Scanning',async()=>{setDevices([]);await Bluetooth.scan(p=>setDevices(old=>[...old.filter(d=>d.id!==p.id),p]));})}/>{state.phase!=='connected'&&devices.map(d=><Pressable style={s.device} key={d.id} disabled={!!busy} onPress={()=>run('Connecting',async()=>{const transport=await Bluetooth.connect(d.id,b=>session.receive(b),message=>{void session.disconnect(message);});pending.current=[];await session.connect(transport,d.name);fileSource.current=null;setSummary(null);setFrames([]);setFileName('');setTab('Capture');})}><Text style={s.deviceName}>{d.name}</Text><Text style={s.blue}>Connect →</Text></Pressable>)}{state.phase==='connected'&&<><Text style={s.detail}>{state.name} · {state.capabilities?.fw}</Text><Button title="Disconnect phone" secondary disabled={!!busy} onPress={()=>run('Disconnecting',()=>session.disconnect())}/></>}</View><View style={s.card}><Text style={s.section}>Passive SCI receive</Text><Text style={s.copy}>Pin and speed are recorded with every raw SCI burst.</Text><View style={s.pills}>{['Off','OBD 7','OBD 15'].map((name,i)=><Pill key={name} title={name} selected={route===i} onPress={()=>setRoute(i)}/>)}</View><View style={s.pills}>{[976,7812,62500,125000].map((baud,i)=><Pill key={baud} title={String(baud)} selected={speed===i} onPress={()=>setSpeed(i)}/>)}</View><Button title="Apply receive path" disabled={!ready||!!busy||state.status?.owner===1} onPress={()=>run('Applying',()=>session.setSci(route,speed))}/><Text style={s.detail}>Control: {state.status?.owner===1?'USB desktop':state.status?.owner===2?'This phone':'Available'}</Text><Button title="Release control" secondary disabled={!fresh||!!busy||!state.capabilities?.lease||state.status?.owner!==2} onPress={()=>run('Releasing',()=>session.releaseControl())}/></View></>:<>
    {fileSource.current?<View style={s.card}><Text style={s.section}>Imported recording</Text><Text style={s.cardTitle}>{summary?.frames.toLocaleString()} frames</Text><Text style={s.copy}>{summary?.cleanStop?'Clean stop recorded':'Recovery / incomplete stop'} · {summary?.skippedBytes} skipped bytes · {summary?.sequenceGaps} gaps{summary?.reportedLoss?` · ${summary.reportedLoss} source-reported drops`:''}</Text><Button title="Export all frames as CSV" onPress={exportFile} disabled={!!busy}/><Button title="Return to live capture" secondary onPress={()=>{fileSource.current=null;setSummary(null);setFrames([]);setFileName('');setTab('Capture');}}/></View>:Platform.OS!=='web'&&tab==='Capture'?<View style={s.card}><View style={s.cardRow}><Text style={s.section}>Board microSD</Text><View style={[s.dot,state.status?.logging&&s.recordingDot]}/></View><Text style={s.cardTitle}>{!fresh?'Connect to view status':state.status?.sdError?'Card error':state.status?.logging?'Recording':state.status?.sdBusy?'Finishing work…':'Stopped'}</Text><Text style={s.copy}>Recording continues without your phone.</Text><View style={s.actions}><Button title={busy==='Starting'?'Starting…':'Start recording'} disabled={!ready||!!busy||state.status?.owner===1} onPress={()=>run('Starting',()=>session.setLogging(true))}/><Button title={busy==='Stopping'?'Finishing writes…':'Stop & confirm'} secondary disabled={!fresh||!!busy||state.status?.owner===1} onPress={()=>run('Stopping',()=>session.setLogging(false))}/></View>{state.safeToRemove&&fresh&&<Text style={s.success}>✓ SD stop confirmed at last check. Do not restart recording before removing the card.</Text>}{state.status?.owner===1&&<Text style={s.detail}>Desktop has control. Release it there to use mobile controls.</Text>}<Text style={s.detail}>{fresh?`USB drops ${state.status?.lost[0]} · SD ${state.status?.lost[1]} · BLE ${state.status?.bleLost}`:'Use Device to connect over Bluetooth.'}</Text></View>:null}
    {!!captures.length&&<View style={s.card}><View style={s.cardRow}><View><Text style={s.section}>Broadcast profile</Text><Text style={s.detail}>Historical Chrysler formulas</Text></View><Switch accessibilityLabel="Historical Chrysler formulas" value={profile} onValueChange={setProfile} trackColor={{true:'#005ecb'}}/></View><Text style={s.fine}>Selected original-project definitions. Confirm applicability to your vehicle.</Text>{metrics.map(m=><View style={s.metric} key={m.label}><Text style={s.copy}>{m.label}</Text><Text style={s.metricValue}>{m.value.toFixed(1)} <Text style={s.unit}>{m.unit}</Text></Text></View>)}</View>}<View style={s.listHeader}><Text style={s.section}>{fileSource.current?'Recording frames':'Latest frames'}</Text>{summary&&<Pressable accessibilityRole="button" onPress={importFile} disabled={!!busy}><Text style={s.blue}>Open another recording</Text></Pressable>}</View>
    </>}
  </View>} renderItem={({item:c})=><View style={s.frame}><View style={s.cardRow}><Text style={[s.bus,c.bus==='SCI'?s.sci:c.bus==='PCI'?s.pci:null]}>{c.bus}</Text><Text style={s.time}>{(c.ms/1000).toFixed(3)} s</Text></View><Text style={s.hex}>{c.hex}</Text><Text style={s.fine}>{c.obdPin?`OBD ${c.obdPin} · ${c.baud} baud`:c.validated?'Checksum verified':'Raw / unverified'} · {c.description}</Text></View>} ListEmptyComponent={tab==='Device'?undefined:<View style={s.empty}><Text style={s.cardTitle}>{fresh?'Listening for traffic':'No frames in view'}</Text><Text style={[s.copy,{textAlign:'center'}]}>Open a .cbr capture to inspect its frames and export CSV.</Text></View>} ListFooterComponent={<Text style={s.footer}>{busy?`${busy}…`:'Receive-only · vehicle transmission disabled'}{tab!=='Device'?`\nLatest 300 shown · ${frames.length} retained`:''}</Text>}/></SafeAreaView>;
}
function Button({title,onPress,disabled=false,secondary=false}:{title:string;onPress:()=>void;disabled?:boolean;secondary?:boolean}){return <Pressable accessibilityRole="button" accessibilityState={{disabled}} disabled={disabled} onPress={onPress} style={[s.button,secondary&&s.secondary,disabled&&s.disabled]}><Text style={[s.buttonText,secondary&&s.secondaryText]}>{title}</Text></Pressable>;}
function Pill({title,selected,onPress}:{title:string;selected:boolean;onPress:()=>void}){return <Pressable accessibilityRole="button" accessibilityState={{selected}} onPress={onPress} style={[s.pill,selected&&s.pillActive]}><Text style={[s.pillText,selected&&s.blue]}>{title}</Text></Pressable>;}

const channels = [
  {id:'CCD', label:'Chrysler CCD', color:'#28784a'},
  {id:'PCI', label:'PCI VPW', color:'#9e5004'},
  {id:'SCI', label:'Raw SCI', color:'#006784'},
] as const;

function BusActivity({frames,imported}:{frames:Capture[];imported:boolean}){
  const rows=useMemo(()=>{
    const latest=frames.at(-1)?.ms;
    return channels.map(channel=>{
      const bins=Array<number>(24).fill(0);
      for(const frame of frames){
        if(latest===undefined||frame.bus!==channel.id)continue;
        const age=(latest-frame.ms)>>>0;
        if(age<12000)bins[23-Math.floor(age/500)]++;
      }
      return {...channel,bins,count:bins.reduce((n,bin)=>n+bin,0)};
    });
  },[frames]);
  return <View style={s.scope}>
    <View style={s.cardRow}>
      <Text style={s.section}>Bus activity</Text>
      <Text style={s.scopeMeta}>{imported?'Recording':'Capture'} · Last 12 s</Text>
    </View>
    <Text style={s.scopeTotal}>{rows.reduce((n,row)=>n+row.count,0).toLocaleString()} <Text style={s.unit}>frames in view</Text></Text>
    {rows.map(row=><View key={row.id} style={s.lane} accessible accessibilityLabel={`${row.label}, ${row.count} frames in view`}>
      <Text style={[s.laneName,{color:row.color}]}>{row.id}</Text>
      <View style={s.bins} aria-hidden={true}>
        {row.bins.map((count,index)=><View key={index} style={s.bin}>
          <View style={{height:count?Math.min(24,4+count*3):2,backgroundColor:count?row.color:'#d8dce3'}}/>
        </View>)}
      </View>
      <Text style={[s.laneCount,{color:row.color}]}>{row.count}</Text>
    </View>)}
    <View style={[s.cardRow,s.scopeFoot]}>
      <Text style={s.scopeMeta}>−12 s</Text>
      <Text style={s.scopeMeta}>{frames.length?'Latest frame':'Waiting for data'}</Text>
    </View>
  </View>;
}

const mono=Platform.OS==='ios'?'Menlo':'monospace';
const ink='#17181b',muted='#555b65',line='#e3e5ea',panel='#ffffff',accent='#005ecb';
const s=StyleSheet.create({
  safe:{flex:1,backgroundColor:'#f2f2f7'},
  header:{paddingHorizontal:22,paddingVertical:17,flexDirection:'row',gap:12,alignItems:'center',backgroundColor:'#ffffff'},
  logo:{width:36,height:36,borderRadius:8},
  brand:{fontSize:16,fontWeight:'700',color:ink},
  subtitle:{fontSize:12,color:muted,marginTop:5},
  badge:{marginLeft:'auto',paddingHorizontal:8,paddingVertical:6,borderRadius:4,backgroundColor:'#eceef3'},
  green:{backgroundColor:'#daf3e1'},
  badgeText:{fontSize:12,color:ink},
  navigation:{backgroundColor:'#ffffff',paddingHorizontal:20,paddingBottom:11,borderBottomWidth:1,borderColor:line},
  tabs:{flexDirection:'row',alignSelf:'center',width:'100%',maxWidth:460,backgroundColor:'#eceef3',padding:3,borderRadius:12},
  tab:{flex:1,alignItems:'center',justifyContent:'center',minHeight:38,borderRadius:9},
  tabActive:{backgroundColor:'#ffffff'},
  tabText:{fontSize:14,color:muted},
  tabTextActive:{color:accent,fontWeight:'700'},
  content:{padding:20,paddingBottom:35,maxWidth:1000,width:'100%',alignSelf:'center'},
  title:{fontSize:34,fontWeight:'800',letterSpacing:-1.1,color:ink,marginTop:6},
  copy:{fontSize:14,lineHeight:21,color:muted,marginVertical:7},
  scope:{padding:16,backgroundColor:'#ffffff',borderWidth:1,borderColor:line,borderRadius:18,marginTop:14},
  scopeMeta:{fontSize:12,color:muted},
  scopeTotal:{fontSize:34,fontWeight:'700',letterSpacing:-1,color:ink,marginTop:4,fontVariant:['tabular-nums']},
  lane:{flexDirection:'row',alignItems:'center',gap:10,marginTop:9},
  laneName:{width:31,fontFamily:mono,fontWeight:'700',fontSize:11},
  laneCount:{minWidth:37,textAlign:'right',fontFamily:mono,fontSize:11},
  bins:{flex:1,flexDirection:'row',height:24,gap:2},
  bin:{flex:1,justifyContent:'flex-end',backgroundColor:'#f1f2f6'},
  scopeFoot:{marginTop:10},
  card:{padding:17,backgroundColor:panel,borderWidth:1,borderColor:line,borderRadius:18,marginTop:14},
  section:{fontSize:15,fontWeight:'700',color:ink},
  cardTitle:{fontSize:21,fontWeight:'700',color:ink,marginTop:9},
  cardRow:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',gap:8},
  dot:{width:8,height:8,borderRadius:4,backgroundColor:'#7e9199'},
  recordingDot:{backgroundColor:'#ff9286'},
  actions:{flexDirection:'row',gap:9,flexWrap:'wrap'},
  button:{backgroundColor:accent,paddingVertical:12,paddingHorizontal:15,borderRadius:12,marginTop:11,minHeight:44,alignItems:'center',justifyContent:'center'},
  secondary:{backgroundColor:'#e9edf4',borderWidth:1,borderColor:line},
  buttonText:{fontSize:13,fontWeight:'700',color:'#ffffff'},
  secondaryText:{color:ink},
  disabled:{opacity:.46},
  success:{fontSize:13,color:'#28784a',marginTop:12,lineHeight:20},
  detail:{fontSize:12,lineHeight:19,color:muted,marginTop:7},
  fine:{fontSize:11,lineHeight:17,color:muted,marginTop:6},
  metric:{borderTopWidth:1,borderColor:line,marginTop:10,paddingTop:5},
  metricValue:{fontFamily:mono,fontSize:24,color:ink,fontWeight:'600'},
  unit:{fontSize:12,color:muted},
  listHeader:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',marginTop:22,marginBottom:9},
  blue:{color:accent,fontSize:12,fontWeight:'700'},
  frame:{padding:13,backgroundColor:panel,borderBottomWidth:1,borderColor:line},
  bus:{fontFamily:mono,fontSize:10,fontWeight:'700',letterSpacing:1,color:'#28784a',backgroundColor:'#e2f4e8',paddingVertical:4,paddingHorizontal:7,borderRadius:4},
  pci:{color:'#9e5004',backgroundColor:'#fff1dd'},
  sci:{color:'#006784',backgroundColor:'#dff1f7'},
  time:{fontFamily:mono,fontSize:11,color:muted},
  hex:{fontFamily:mono,fontSize:13,lineHeight:21,color:ink,marginTop:9},
  empty:{alignItems:'center',padding:18,borderWidth:1,borderColor:line,borderRadius:8},
  footer:{textAlign:'center',fontFamily:mono,fontSize:10,lineHeight:18,color:muted,marginTop:17},
  device:{flexDirection:'row',justifyContent:'space-between',paddingVertical:15,borderTopWidth:1,borderColor:line,marginTop:12},
  deviceName:{fontSize:14,color:ink},
  pills:{flexDirection:'row',gap:7,flexWrap:'wrap',marginTop:11},
  pill:{paddingVertical:10,paddingHorizontal:12,backgroundColor:'#e9edf4',borderRadius:5},
  pillActive:{backgroundColor:'#dceaff'},
  pillText:{fontSize:12,color:muted},
  error:{padding:13,backgroundColor:'#472c29'},
  errorText:{color:'#ffd3cc',fontSize:13,lineHeight:19},
});
