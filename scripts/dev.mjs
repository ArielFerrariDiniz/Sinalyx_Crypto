import { accessSync, constants, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createServer } from 'node:net';
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const frontend = resolve(root, 'frontend');
const children = [];
let stopping = false;
let killTimer;
let keyboard;

function signalGroup(child, signal) {
  if (!child.pid) return;
  try { process.kill(-child.pid, signal); }
  catch (error) { if (error.code !== 'ESRCH') console.error(`[dev] Falha ao encerrar ${child.name}: ${error.message}`); }
}

function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  keyboard?.close();
  if (children.some(child => !child.closed)) {
    console.log('\n[dev] Encerrando backend e frontend…');
    for (const child of children) signalGroup(child, 'SIGINT');
    killTimer = setTimeout(() => {
      for (const child of children) signalGroup(child, 'SIGKILL');
    }, 5000);
  }
}

process.on('SIGINT', () => shutdown());
process.on('SIGTERM', () => shutdown());
process.on('SIGHUP', () => shutdown());

keyboard = createInterface({ input: process.stdin, crlfDelay: Infinity });
keyboard.on('line', line => {
  if (line.trim().toLowerCase() !== 'o' || stopping) return;
  const browser = spawn('xdg-open', ['http://127.0.0.1:5173'], {
    detached: true, stdio: 'ignore',
  });
  browser.once('error', error => console.error(`[dev] Não foi possível abrir o navegador: ${error.message}`));
  browser.unref();
});

function start(name, command, args, cwd) {
  if (stopping) return;
  const child = spawn(command, args, {
    cwd, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });
  child.name = name;
  child.closed = false;
  createInterface({ input: child.stdout, crlfDelay: Infinity })
    .on('line', line => console.log(`[${name}] ${line}`));
  createInterface({ input: child.stderr, crlfDelay: Infinity })
    .on('line', line => console.error(`[${name}] ${line}`));
  children.push(child);
  child.on('error', error => {
    console.error(`[dev] Não foi possível iniciar ${name}: ${error.message}`);
    shutdown(1);
  });
  child.on('close', (code, signal) => {
    child.closed = true;
    if (!stopping) {
      console.error(`[dev] ${name} encerrou inesperadamente (${signal ?? `código ${code}`}).`);
      shutdown(1);
    }
    if (children.every(item => item.closed)) clearTimeout(killTimer);
  });
}

function findPython() {
  for (const directory of ['.venv', 'backend/.venv']) {
    const executable = resolve(root, directory, 'bin/python');
    try {
      accessSync(executable, constants.X_OK);
      return executable;
    } catch { /* Tenta a outra localização suportada. */ }
  }
  throw new Error('Ambiente Python ausente. Crie .venv na raiz com "python3.13 -m venv .venv" e instale ".venv/bin/python -m pip install -r backend/requirements.txt". Também é aceito backend/.venv.');
}

function checkPython(python) {
  const probe = spawnSync(python, ['-c', [
    'import importlib, json, sys',
    'missing = []',
    'for name in ("fastapi", "httpx", "pydantic", "uvicorn", "secretstorage"): ',
    '    try: importlib.import_module(name)',
    '    except Exception: missing.append(name)',
    'print(json.dumps({"version": list(sys.version_info[:2]), "missing": missing}))',
  ].join('\n')], { cwd: root, encoding: 'utf8', timeout: 10000 });
  let info;
  try { info = JSON.parse(probe.stdout); } catch { /* Mensagem segura abaixo. */ }
  if (probe.error || probe.status !== 0 || !info) {
    throw new Error(`Não foi possível verificar o ambiente Python em ${python}. Recrie a .venv com Python 3.13 e instale backend/requirements.txt.`);
  }
  if (info.version[0] !== 3 || info.version[1] !== 13) {
    throw new Error(`O ambiente ${python} precisa utilizar Python 3.13.`);
  }
  if (info.missing.length) {
    throw new Error(`Dependências Python ausentes ou inválidas: ${info.missing.join(', ')}. Execute "${python} -m pip install -r backend/requirements.txt".`);
  }
}

function checkFrontend() {
  const require = createRequire(resolve(frontend, 'package.json'));
  const missing = [];
  for (const name of ['vite', 'react', 'react-dom', '@vitejs/plugin-react', 'typescript']) {
    try { require.resolve(name); } catch { missing.push(name); }
  }
  const vite = resolve(frontend, 'node_modules/vite/bin/vite.js');
  if (missing.length || !existsSync(vite)) {
    throw new Error(`Dependências do frontend ausentes${missing.length ? `: ${missing.join(', ')}` : ''}. Execute "npm ci --prefix frontend" na raiz.`);
  }
  return vite;
}

async function checkPort(port) {
  await new Promise((done, reject) => {
    const server = createServer();
    server.once('error', error => reject(new Error(error.code === 'EADDRINUSE'
      ? `Porta ${port} já está em uso. Encerre o serviço que a ocupa antes de executar npm run dev. Nenhum serviço foi iniciado.`
      : `Não foi possível verificar a porta ${port}: ${error.message}`)));
    server.listen({ host: '127.0.0.1', port, exclusive: true }, () => server.close(done));
  });
}

try {
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (!(major === 20 && minor >= 19 || major === 22 && minor >= 12 || major > 22)) {
    throw new Error('Utilize Node.js 20.19+ ou 22.12+ para executar o Vite.');
  }
  const python = findPython();
  checkPython(python);
  const vite = checkFrontend();
  await checkPort(8000);
  await checkPort(5173);
  if (!stopping) {
    console.log(`[dev] Python: ${python}`);
    console.log('[dev] Backend: http://127.0.0.1:8000 | Frontend: http://127.0.0.1:5173');
    if (process.stdin.isTTY) console.log('[dev] Digite o + Enter para abrir o aplicativo no navegador.');
    console.log('[dev] Ctrl+C encerra ambos os serviços. Logs abaixo:');
    start('backend', python, [
      '-u', '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
      '--host', '127.0.0.1', '--port', '8000', '--no-proxy-headers', '--no-access-log',
    ], root);
    start('frontend', process.execPath, [vite, '--host', '127.0.0.1', '--port', '5173', '--strictPort'], frontend);
  }
} catch (error) {
  console.error(`[dev] ${error.message}`);
  shutdown(1);
}
