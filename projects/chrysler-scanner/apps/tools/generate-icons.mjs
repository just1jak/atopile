import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import electron from 'electron';
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const result=spawnSync(electron,[fileURLToPath(new URL('./icon-main.cjs',import.meta.url))],{env,stdio:'inherit',windowsHide:true});
process.exitCode=result.status??1;
