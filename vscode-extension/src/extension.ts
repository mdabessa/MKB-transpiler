import * as vscode from 'vscode';
import { execFile } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

/**
 * MKB Macro Language
 *
 * Diagnostics come from the Python tools, not from a reimplementation:
 *   .mkb          -> tools/lint_mkb.py   (source-level linter)
 *   .txt scripts  -> tools/validate.py   (generated-language validator)
 *
 * Both accept `-` and read the unsaved buffer from stdin, so what you see in
 * the editor is what gets linted.
 */

type SeverityName = 'error' | 'warning' | 'info';

interface KeywordEntry {
  category: string;
  name: string;
  definition: string;
  varnames: string[];
  description: string;
}

interface DiagnosticDto {
  file: string;
  line: number;
  col: number;
  severity: SeverityName;
  code: string;
  message: string;
}

const MKB = 'mkb';
const SCRIPT = 'macroscript';
const LANGUAGES = [MKB, SCRIPT];
const DEBOUNCE_MS = 400;

let collection: vscode.DiagnosticCollection;
let statusItem: vscode.StatusBarItem;
let keywords: Map<string, KeywordEntry> | undefined;
let toolProblemShown = false;
const timers = new Map<string, ReturnType<typeof setTimeout>>();

// --------------------------------------------------------------------------
// activation
// --------------------------------------------------------------------------

export function activate(context: vscode.ExtensionContext): void {
  collection = vscode.languages.createDiagnosticCollection(MKB);
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusItem.command = 'mkb.lint';
  statusItem.text = '$(check) MKB';

  context.subscriptions.push(
    collection,
    statusItem,
    vscode.commands.registerCommand('mkb.lint', () => {
      const document = vscode.window.activeTextEditor?.document;
      if (document && LANGUAGES.includes(document.languageId)) {
        void lint(document);
      } else {
        void vscode.window.showInformationMessage(
          'The active file is not an MKB macro or a macro script.',
        );
      }
    }),
    vscode.commands.registerCommand('mkb.lintWorkspace', () => lintWorkspace()),
    vscode.workspace.onDidOpenTextDocument(document => schedule(document)),
    vscode.workspace.onDidSaveTextDocument(document => {
      if (LANGUAGES.includes(document.languageId)) {
        void lint(document);
      }
    }),
    vscode.workspace.onDidChangeTextDocument(event => {
      if (!LANGUAGES.includes(event.document.languageId)) {
        return;
      }
      if (config().get<boolean>('lintOnType', true)) {
        schedule(event.document);
      } else {
        collection.delete(event.document.uri);
      }
    }),
    vscode.workspace.onDidCloseTextDocument(document => {
      timers.delete(document.uri.toString());
      collection.delete(document.uri);
    }),
    vscode.languages.registerCompletionItemProvider(LANGUAGES, new KeywordCompletion()),
    vscode.languages.registerHoverProvider(LANGUAGES, new KeywordHover()),
    vscode.languages.registerSignatureHelpProvider(LANGUAGES, new KeywordSignatureHelp(), '(', ','),
  );

  for (const document of vscode.workspace.textDocuments) {
    schedule(document);
  }

  if (config().get<boolean>('lintWorkspaceOnStartup', false)) {
    void lintWorkspace();
  }
}

export function deactivate(): void {
  for (const timer of timers.values()) {
    clearTimeout(timer);
  }
  timers.clear();
}

// --------------------------------------------------------------------------
// linting
// --------------------------------------------------------------------------

function schedule(document: vscode.TextDocument): void {
  if (!LANGUAGES.includes(document.languageId)) {
    return;
  }
  const key = document.uri.toString();
  const existing = timers.get(key);
  if (existing) {
    clearTimeout(existing);
  }
  timers.set(
    key,
    setTimeout(() => {
      timers.delete(key);
      void lint(document);
    }, DEBOUNCE_MS),
  );
}

async function lint(document: vscode.TextDocument): Promise<void> {
  const root = rootPath();
  if (!root) {
    return;
  }

  const isScript = document.languageId === SCRIPT;
  if (isScript && !config().get<boolean>('validateScripts', true)) {
    collection.delete(document.uri);
    return;
  }

  const tool = isScript ? 'validate.py' : 'lint_mkb.py';
  try {
    const output = await runTool(root, tool, [
      '-',
      '--stdin-name',
      document.uri.fsPath,
      '--format',
      'json',
    ], document.getText());

    const items = parseDiagnostics(output);
    collection.set(document.uri, items.map(toDiagnostic));
    updateStatus(document, items);
  } catch (error) {
    reportToolProblem(root, error);
  }
}

async function lintWorkspace(): Promise<void> {
  const root = rootPath();
  if (!root) {
    return;
  }

  const pattern = new vscode.RelativePattern(root, 'macros/**/*.mkb');
  const files = await vscode.workspace.findFiles(pattern, '**/node_modules/**');
  if (files.length === 0) {
    void vscode.window.showInformationMessage('No .mkb files found under macros/.');
    return;
  }

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Window, title: 'Linting MKB macros' },
    async progress => {
      let errors = 0;
      for (let index = 0; index < files.length; index += 1) {
        progress.report({ message: `${index + 1}/${files.length}`, increment: 100 / files.length });
        try {
          const document = await vscode.workspace.openTextDocument(files[index]);
          await lint(document);
          errors += countErrors(collection.get(files[index]));
        } catch {
          // A file that cannot be opened is reported by the linter itself.
        }
      }
      void vscode.window.showInformationMessage(
        errors === 0
          ? `MKB: ${files.length} file(s) linted, no errors.`
          : `MKB: ${files.length} file(s) linted, ${errors} error(s).`,
      );
    },
  );
}

function countErrors(diagnostics: readonly vscode.Diagnostic[] | undefined): number {
  return (diagnostics ?? []).filter(d => d.severity === vscode.DiagnosticSeverity.Error).length;
}

function toDiagnostic(item: DiagnosticDto): vscode.Diagnostic {
  const line = Math.max(0, item.line - 1);
  const column = Math.max(0, item.col - 1);
  const range = new vscode.Range(line, column, line, column + 1);
  const severity =
    item.severity === 'error'
      ? vscode.DiagnosticSeverity.Error
      : item.severity === 'warning'
        ? vscode.DiagnosticSeverity.Warning
        : vscode.DiagnosticSeverity.Information;

  const diagnostic = new vscode.Diagnostic(range, item.message, severity);
  diagnostic.code = item.code;
  diagnostic.source = 'mkb';
  return diagnostic;
}

function updateStatus(document: vscode.TextDocument, items: DiagnosticDto[]): void {
  const errors = items.filter(item => item.severity === 'error').length;
  const warnings = items.filter(item => item.severity === 'warning').length;
  const infos = items.filter(item => item.severity === 'info').length;

  statusItem.text = errors
    ? `$(error) MKB ${errors}`
    : warnings
      ? `$(warning) MKB ${warnings}`
      : '$(check) MKB';
  statusItem.tooltip = `${path.basename(document.uri.fsPath)}: ${errors} error(s), ` +
    `${warnings} warning(s), ${infos} info`;
  statusItem.show();
}

// --------------------------------------------------------------------------
// running the python tools
// --------------------------------------------------------------------------

function config(): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration(MKB);
}

function rootPath(): string | undefined {
  const folders = vscode.workspace.workspaceFolders ?? [];
  for (const folder of folders) {
    if (fs.existsSync(path.join(folder.uri.fsPath, 'functions.json'))) {
      return folder.uri.fsPath;
    }
  }
  return folders[0]?.uri.fsPath;
}

function runTool(root: string, script: string, args: string[], stdin: string): Promise<string> {
  const toolPath = path.join(root, 'tools', script);
  if (!fs.existsSync(toolPath)) {
    return Promise.reject(new Error(`not found: ${toolPath}`));
  }

  const python = config().get<string>('pythonPath', 'python3');
  const timeout = config().get<number>('timeoutMs', 15000);

  return new Promise((resolve, reject) => {
    const child = execFile(
      python,
      [toolPath, ...args],
      { cwd: root, timeout, maxBuffer: 16 * 1024 * 1024 },
      (error, stdout) => {
        // Exit code 1 means "found problems"; the JSON on stdout is still valid.
        const spawnFailure = (error as NodeJS.ErrnoException | null)?.code;
        if (spawnFailure === 'ENOENT') {
          reject(new Error(`Python interpreter not found: ${python}`));
          return;
        }
        if (error && !stdout) {
          reject(new Error(error.message));
          return;
        }
        resolve(stdout);
      },
    );
    child.stdin?.end(stdin);
  });
}

function parseDiagnostics(output: string): DiagnosticDto[] {
  const start = output.indexOf('[');
  const end = output.lastIndexOf(']');
  if (start === -1 || end === -1 || end < start) {
    throw new Error('the linter did not return JSON');
  }
  return JSON.parse(output.slice(start, end + 1)) as DiagnosticDto[];
}

function reportToolProblem(root: string, error: unknown): void {
  if (toolProblemShown) {
    return;
  }
  toolProblemShown = true;
  const detail = error instanceof Error ? error.message : String(error);
  statusItem.text = '$(error) MKB';
  statusItem.tooltip = detail;
  statusItem.show();
  void vscode.window.showWarningMessage(
    `MKB: could not run the linter in ${root} (${detail}). ` +
    'Check "mkb.pythonPath" and that tools/lint_mkb.py exists.',
  );
}

// --------------------------------------------------------------------------
// keyword data (functions.json)
// --------------------------------------------------------------------------

function loadKeywords(): Map<string, KeywordEntry> {
  if (keywords) {
    return keywords;
  }
  keywords = new Map();
  const root = rootPath();
  if (!root) {
    return keywords;
  }
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(root, 'functions.json'), 'utf8')) as
      Record<string, KeywordEntry>;
    for (const [key, entry] of Object.entries(raw)) {
      const name = key.replace(/\(\)$/, '').toUpperCase();
      keywords.set(name, { ...entry, name });
    }
  } catch {
    // No inventory: completion and hover simply stay empty.
  }
  return keywords;
}

function keywordAt(document: vscode.TextDocument, position: vscode.Position): KeywordEntry | undefined {
  const range = document.getWordRangeAtPosition(position, /[A-Za-z_][A-Za-z0-9_]*/);
  if (!range) {
    return undefined;
  }
  return loadKeywords().get(document.getText(range).toUpperCase());
}

class KeywordCompletion implements vscode.CompletionItemProvider {
  provideCompletionItems(document: vscode.TextDocument, position: vscode.Position): vscode.CompletionItem[] {
    const entries = [...loadKeywords().values()];
    entries.sort((left, right) => left.name.localeCompare(right.name));

    return entries.map(entry => {
      const item = new vscode.CompletionItem(entry.name, vscode.CompletionItemKind.Function);
      item.detail = entry.definition;
      const documentation = new vscode.MarkdownString();
      documentation.appendMarkdown(`**\`${entry.definition}\`**\n\n`);
      documentation.appendText(entry.description);
      documentation.appendMarkdown(`\n\n*Category: ${entry.category}*`);
      item.documentation = documentation;
      item.filterText = entry.name;
      item.insertText = entry.name;
      item.sortText = `${entry.category}-${entry.name}`;
      // Only complete the opening parenthesis when the keyword needs arguments.
      if (entry.varnames && entry.varnames.length > 0) {
        item.command = {
          command: 'editor.action.triggerSuggest',
          title: 'Argument',
        };
      }
      return item;
    });
  }
}

class KeywordHover implements vscode.HoverProvider {
  provideHover(document: vscode.TextDocument, position: vscode.Position): vscode.Hover | undefined {
    const entry = keywordAt(document, position);
    if (!entry) {
      return undefined;
    }
    const markdown = new vscode.MarkdownString();
    markdown.appendMarkdown(`**\`${entry.definition}\`**\n\n`);
    markdown.appendText(entry.description);
    markdown.appendMarkdown(`\n\n*Category: ${entry.category}*`);
    return new vscode.Hover(markdown);
  }
}

class KeywordSignatureHelp implements vscode.SignatureHelpProvider {
  provideSignatureHelp(document: vscode.TextDocument, position: vscode.Position): vscode.SignatureHelp | undefined {
    const line = document.lineAt(position.line).text.slice(0, position.character);

    let depth = 0;
    let open = -1;
    for (let index = line.length - 1; index >= 0; index -= 1) {
      const char = line[index];
      if (char === ')') {
        depth += 1;
      } else if (char === '(') {
        if (depth === 0) {
          open = index;
          break;
        }
        depth -= 1;
      }
    }
    if (open < 0) {
      return undefined;
    }

    const nameMatch = /([A-Za-z_][A-Za-z0-9_]*)\s*$/.exec(line.slice(0, open));
    if (!nameMatch) {
      return undefined;
    }
    const entry = loadKeywords().get(nameMatch[1].toUpperCase());
    if (!entry) {
      return undefined;
    }

    const parameters = (entry.varnames ?? []).map(
      parameter => new vscode.ParameterInformation(parameter),
    );
    const signature = new vscode.SignatureInformation(entry.definition, entry.description);
    signature.parameters = parameters;

    const help = new vscode.SignatureHelp();
    help.signatures = [signature];
    help.activeSignature = 0;
    help.activeParameter = Math.min(parameters.length, countArguments(line.slice(open + 1)));
    return help;
  }
}

/** Number of commas at the current nesting level — the active parameter index. */
function countArguments(text: string): number {
  let depth = 0;
  let commas = 0;
  let inString = false;
  let escaped = false;

  for (const char of text) {
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === '\\') {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }
    if (char === '"') {
      inString = true;
    } else if (char === '(') {
      depth += 1;
    } else if (char === ')') {
      depth -= 1;
    } else if (char === ',' && depth === 0) {
      commas += 1;
    }
  }
  return commas;
}
