import {build} from 'esbuild';
await build({entryPoints:['electron/main.ts'],outfile:'dist/main.cjs',bundle:true,platform:'node',format:'cjs',external:['electron','serialport'],target:'node22'});
await build({entryPoints:['electron/preload.ts'],outfile:'dist/preload.cjs',bundle:true,platform:'node',format:'cjs',external:['electron'],target:'node22'});
