import * as vscode from "vscode";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

export function activate(context: vscode.ExtensionContext) {
  const outputChannel = vscode.window.createOutputChannel("Fallow-Like");

  const runCommand = async (args: string) => {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      vscode.window.showErrorMessage("No workspace folder open");
      return;
    }
    const config = vscode.workspace.getConfiguration("fallowLike");
    const pythonPath = config.get<string>("pythonPath", "python3");
    outputChannel.show();
    outputChannel.appendLine(`Running: ${pythonPath} -m skills.fallow_like.cli ${args}`);
    try {
      const { stdout, stderr } = await execAsync(
        `${pythonPath} -m skills.fallow_like.cli ${args}`,
        { cwd: workspaceFolder.uri.fsPath }
      );
      outputChannel.appendLine(stdout);
      if (stderr) outputChannel.appendLine(`STDERR: ${stderr}`);
    } catch (error: any) {
      outputChannel.appendLine(`Error: ${error.message}`);
    }
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("fallowLike.analyze", () =>
      runCommand("analyze . --format text")),
    vscode.commands.registerCommand("fallowLike.health", () =>
      runCommand("health .")),
    vscode.commands.registerCommand("fallowLike.deadCode", () =>
      runCommand("dead-code .")),
    vscode.commands.registerCommand("fallowLike.secrets", () =>
      runCommand("secrets .")),
  );
}

export function deactivate() {}
