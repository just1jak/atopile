import {build} from 'esbuild';
import {spawnSync} from 'node:child_process';
await build({entryPoints:['desktop/ui-smoke.ts'],outfile:'artifacts/ui-smoke.cjs',bundle:true,platform:'node',format:'cjs',external:['electron','playwright'],target:'node22'});
const result=spawnSync(process.execPath,['artifacts/ui-smoke.cjs'],{stdio:'inherit'});process.exitCode=result.status??1;
