import { copyFile, cp, mkdir, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { delimiter, join } from "node:path";

const watch = process.argv.includes("--watch");

const appRoot = fileURLToPath(new URL("../../../../", import.meta.url));
const webviewRoot = fileURLToPath(new URL("../", import.meta.url));
const outDirUrl = new URL("../../../vscode-atopile/webview-dist/", import.meta.url);
const outDir = fileURLToPath(outDirUrl);

const assets = [
  ["../common/logo.png", "logo.png"],
  ["../common/logo-dark.svg", "logo-dark.svg"],
  ["../common/logo-light.svg", "logo-light.svg"],
  ["../sidebar-details/assets/occt-import-js.wasm", "occt-import-js.wasm"],
  ["../sidebar-details/assets/model-viewer.min.js", "model-viewer.min.js"],
] as const;
const entrypoints = await Array.fromAsync(
  new Bun.Glob("*/main.tsx").scan({
    cwd: webviewRoot,
    onlyFiles: true,
  }),
);

if (entrypoints.length === 0) {
  throw new Error(`No webview entrypoints found under ${webviewRoot}`);
}

await run(
  [process.env.ATOPILE_LOCAL_PYTHON || join(appRoot, ".venv", "bin", "python"), "-P", "-m", "atopile.generate_types"],
  appRoot,
);

if (!watch) {
  await rm(outDir, { force: true, recursive: true });
}
await mkdir(outDir, { recursive: true });
await copyAssets();
await cp(fileURLToPath(new URL("../node_modules/three/examples/jsm/libs/draco/gltf/", import.meta.url)), fileURLToPath(new URL("draco/", outDirUrl)), { recursive: true });
await copyFile(fileURLToPath(new URL("../node_modules/three/examples/jsm/libs/draco/README.md", import.meta.url)), fileURLToPath(new URL("draco/README.md", outDirUrl)));
await copyFile(fileURLToPath(new URL("../../../vscode-atopile/resources/DRACO-LICENSE", import.meta.url)), fileURLToPath(new URL("draco/LICENSE", outDirUrl)));
await copyFile(fileURLToPath(new URL("../node_modules/three/LICENSE", import.meta.url)), fileURLToPath(new URL("THREE-LICENSE", outDirUrl)));

const buildArgs = [
  process.execPath,
  "build",
  ...entrypoints,
  "--root",
  webviewRoot,
  "--outdir",
  outDir,
  "--entry-naming",
  "[dir]/index.[ext]",
  "--chunk-naming",
  "chunks/[name]-[hash].[ext]",
  "--splitting",
  "--format",
  "esm",
];

if (watch) {
  buildArgs.push("--watch");
} else {
  buildArgs.push("--minify");
}

// A Blob worker cannot resolve shared relative chunks. Keep its geometry bundle standalone.
const workerArgs = [process.execPath, "build", join(webviewRoot, "panel-schematic/geometry.worker.ts"),
  "--outfile", join(outDir, "panel-schematic/geometry.worker.js"), "--format", "iife", "--target", "browser", "--minify"];
if (watch) {
  Bun.spawn([...workerArgs, "--watch"], { cwd: webviewRoot, stdin: "inherit", stdout: "inherit", stderr: "inherit" });
} else {
  await run(workerArgs, webviewRoot);
}
await run(buildArgs, webviewRoot);

async function copyAssets(): Promise<void> {
  await Promise.all(
    assets.map(([source, target]) =>
      copyFile(
        fileURLToPath(new URL(source, import.meta.url)),
        fileURLToPath(new URL(target, outDirUrl)),
      ),
    ),
  );
}

async function run(cmd: string[], cwd: string): Promise<void> {
  const proc = Bun.spawn(cmd, {
    cwd,
    env: { ...process.env, ATOPILE_LOCAL_MODE: "1", ATOPILE_LOCAL_DATA_DIR: process.env.ATOPILE_LOCAL_DATA_DIR || join(appRoot, ".state"), FBRK_TELEMETRY: "0", MPLCONFIGDIR: join(appRoot, ".state", "matplotlib"), PYTHONPATH: [join(appRoot, "src"), process.env.PYTHONPATH].filter(Boolean).join(delimiter) },
    stdin: "inherit",
    stdout: "inherit",
    stderr: "inherit",
  });
  const exitCode = await proc.exited;
  if (exitCode !== 0) {
    process.exit(exitCode);
  }
}
