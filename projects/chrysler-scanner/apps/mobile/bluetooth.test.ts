import {afterEach,describe,expect,it,vi} from 'vitest';
import {connect} from './bluetooth.native';

const {ble,remove,link} = vi.hoisted(()=>{
  const link:{onDisconnect?:(event:{peripheral:string})=>void}={};
  const remove=vi.fn();
  const ble={
    start:vi.fn().mockResolvedValue(undefined),
    connect:vi.fn(),
    retrieveServices:vi.fn(),
    disconnect:vi.fn().mockResolvedValue(undefined),
    onDisconnectPeripheral:vi.fn((listener:(event:{peripheral:string})=>void)=>{
      link.onDisconnect=listener;
      return {remove};
    }),
  };
  return {ble,remove,link};
});

vi.mock('react-native',()=>({Platform:{OS:'ios'}}));
vi.mock('react-native-ble-manager',()=>({default:ble}));

afterEach(()=>{
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe('mobile BLE setup recovery',()=>{
  it('cancels an iOS connection attempt with no native callback',async()=>{
    vi.useFakeTimers();
    ble.connect.mockImplementation(()=>new Promise(()=>{}));
    const setup=connect('scanner',vi.fn(),vi.fn());
    const result=expect(setup).rejects.toThrow('did not respond');
    await vi.waitFor(()=>expect(ble.connect).toHaveBeenCalledOnce());
    await vi.advanceTimersByTimeAsync(15000);
    await result;
    expect(remove).toHaveBeenCalledOnce();
    expect(ble.disconnect).toHaveBeenCalledWith('scanner');
    expect(ble.retrieveServices).not.toHaveBeenCalled();
  });
  it('aborts setup immediately if the peripheral disconnects during discovery',async()=>{
    ble.connect.mockResolvedValue(undefined);
    ble.retrieveServices.mockImplementation(()=>new Promise(()=>{}));
    const lost=vi.fn();
    const setup=connect('scanner',vi.fn(),lost);
    const result=expect(setup).rejects.toThrow('Bluetooth disconnected');
    await vi.waitFor(()=>expect(ble.retrieveServices).toHaveBeenCalledOnce());
    link.onDisconnect?.({peripheral:'SCANNER'});
    await result;
    expect(remove).toHaveBeenCalledOnce();
    expect(ble.disconnect).toHaveBeenCalledWith('scanner');
    expect(lost).not.toHaveBeenCalled();
  });
});
