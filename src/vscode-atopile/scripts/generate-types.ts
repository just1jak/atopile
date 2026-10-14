import { fileURLToPath } from "node:url";
import { delimiter, join } from "node:path";
const root = fileURLToPath(new URL("../../../", import.meta.url));
const python = process.env.ATOPILE_LOCAL_PYTHON || join(root, ".venv", "bin", "python");
const proc = Bun.spawn([python, "-P", "-m", "atopile.generate_types"], {
  cwd: root,
  env: { ...process.env, ATOPILE_LOCAL_MODE: "1", ATOPILE_LOCAL_DATA_DIR: process.env.ATOPILE_LOCAL_DATA_DIR || join(root, ".state"), FBRK_TELEMETRY: "0", MPLCONFIGDIR: join(root, ".state", "matplotlib"), PYTHONPATH: [join(root, "src"), process.env.PYTHONPATH].filter(Boolean).join(delimiter) },
  stdout: "inherit", stderr: "inherit",
});
process.exit(await proc.exited);
