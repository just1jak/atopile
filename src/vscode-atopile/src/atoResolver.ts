import { execFile } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { promisify } from "util";
import * as vscode from "vscode";
import { ChannelLogger } from "./logger";
import { readRuntimeHandoff } from "./runtimeHandoff";

const execFileAsync = promisify(execFile);

export interface ResolvedBinary {
  /** Path to the executable to launch */
  command: string;
  /** Arguments prepended before any ato subcommand args */
  prefixArgs: string[];
  /** Extra environment variables required to launch the command */
  env?: Record<string, string>;
  /** Whether we're running a configured local ato binary */
  isLocal: boolean;
  /** Resolved absolute path to the ato binary */
  atoBinary?: string;
}

export class AtoNotResolveableMisconfigured extends Error {
  constructor(configuredAto: string) {
    super(
      `Configured ato binary not found: ${configuredAto}. Run setup and fix the atopileLocal.ato launcher setting.`,
    );
    this.name = "AtoNotResolveableMisconfigured";
  }
}

export class AtoNotResolveableWhichFailed extends Error {
  constructor(configuredAto: string, detail: string) {
    super(`Configured ato binary failed verification: ${configuredAto}. ${detail}`);
    this.name = "AtoNotResolveableWhichFailed";
  }
}

export async function resolveAto(
  context: vscode.ExtensionContext,
  logger: ChannelLogger,
  _version: string,
): Promise<ResolvedBinary> {
  const configuredAto = getConfiguredAtoPath(context.extensionPath, context.globalStorageUri.fsPath);
  if (!configuredAto) {
    throw new Error("Atopile Local needs its compiler launcher. Run setup, then set atopileLocal.ato to bin/ato-local. The upstream compiler does not contain this fork's local AI changes.");
  }
  if (!fs.existsSync(configuredAto)) throw new AtoNotResolveableMisconfigured(configuredAto);
  try {
    const atoBinary = await resolveAndVerifyAtoBinary(logger, configuredAto);
    logger.info(`local compiler: ${atoBinary}`);
    return { command: atoBinary, prefixArgs: [], isLocal: true, atoBinary };
  } catch (err) {
    throw new AtoNotResolveableWhichFailed(configuredAto, err instanceof Error ? err.message : String(err));
  }
}

/** Resolve the absolute path to the ato binary and verify it via self-check. */
async function resolveAndVerifyAtoBinary(
  logger: ChannelLogger,
  command: string,
  prefixArgs: string[] = [],
  env?: Record<string, string>,
): Promise<string> {
  const execOptions = { env: { ...process.env, ...env }, encoding: "utf8" as const };
  let atoBinary = command;
  if (prefixArgs.length > 0) {
    const { stdout } = await execFileAsync(
      command,
      [...prefixArgs, "python", "-c", `import shutil; print(shutil.which("ato"))`],
      execOptions,
    );
    const result = stdout.trim();
    if (!result || result === "None") {
      logger.warn("Could not resolve ato binary");
      throw new Error("Could not resolve ato binary");
    }
    atoBinary = result;
  }

  try {
    await execFileAsync(atoBinary, ["self-check"], execOptions);
  } catch (error) {
    const execError = error as Error & { stderr?: string; stdout?: string };
    throw new Error(
      `ato self-check failed: ${execError.stderr?.trim() || execError.stdout?.trim() || execError.message}`,
    );
  }

  return atoBinary;
}

export function getConfiguredAtoPath(extensionPath?: string, runtimeStoragePath?: string): string {
  const rawValue = vscode.workspace.getConfiguration("atopileLocal").get<string>("ato", "")?.trim() ?? "";
  if (!rawValue) {
    const envPath = process.env.ATOPILE_LOCAL_ATO;
    if (envPath) return envPath;
    const installedRuntime = readRuntimeHandoff(runtimeStoragePath);
    if (installedRuntime) return installedRuntime;
    const installedPath = extensionPath ?? vscode.extensions.getExtension("local-atopile.atopile-local")?.extensionPath;
    if (installedPath) {
      const candidates = [path.resolve(installedPath, "../../bin/ato-local"), path.join(installedPath, "bin/ato-local")];
      const found = candidates.find((candidate) => fs.existsSync(candidate));
      if (found) return found;
    }
    return "";
  }
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) return rawValue;
  return rawValue.replace(/\$\{workspace(?:Folder|Root)\}/g, workspaceFolder.uri.fsPath);
}
