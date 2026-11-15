import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { access, chmod, copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import test from 'node:test';

const source = new URL('../scripts/dev.mjs', import.meta.url);

async function put(path, contents) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, contents);
}

async function fixture(options = {}) {
  const root = await mkdtemp(join(tmpdir(), 'crypto-bot-launcher-'));
  await mkdir(join(root, 'scripts'));
  await copyFile(source, join(root, 'scripts/dev.mjs'));
  const service = (name, port) => `
import { createServer } from 'node:net';
import { writeFileSync } from 'node:fs';
const server = createServer(socket => socket.end('test'));
server.listen(${port}, '127.0.0.1', () => {
  writeFileSync(${JSON.stringify(join(root, name + '.pid'))}, String(process.pid));
  console.log('fake ${name} started');
});
process.on('SIGINT', () => server.close(() => process.exit(0)));
process.on('SIGTERM', () => server.close(() => process.exit(0)));
`;
  if (!options.noPython) {
    const python = join(root, options.backendVenv ? 'backend/.venv/bin/python' : '.venv/bin/python');
    await put(python, `#!${process.execPath}
if (process.argv.includes('-c')) {
  console.log(JSON.stringify({version:[3,13], missing:${JSON.stringify(options.missingPython ?? [])}}));
} else {
  await import('data:text/javascript,' + encodeURIComponent(${JSON.stringify(service('backend', 8000))}));
}
`);
    await chmod(python, 0o700);
    // O interpretador de teste é um módulo Node, não um ambiente Python real.
    await put(join(root, 'package.json'), '{"type":"module"}');
  }
  await put(join(root, 'frontend/package.json'), '{"type":"module"}');
  if (!options.noFrontend) {
    for (const name of ['vite', 'react', 'react-dom', '@vitejs/plugin-react', 'typescript']) {
      await put(join(root, 'frontend/node_modules', name, 'package.json'), '{"main":"index.js","type":"module"}');
      await put(join(root, 'frontend/node_modules', name, 'index.js'), 'export default {};');
    }
    await put(join(root, 'frontend/node_modules/vite/bin/vite.js'), options.crashFrontend
      ? 'setTimeout(() => process.exit(7), 300);' : service('frontend', 5173));
  }
  return root;
}

function launch(root) {
  const child = spawn(process.execPath, [join(root, 'scripts/dev.mjs')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let output = '';
  child.stdout.on('data', data => { output += data; });
  child.stderr.on('data', data => { output += data; });
  const closed = once(child, 'close').then(([code]) => code);
  return { child, closed, output: () => output };
}

async function waitFor(condition) {
  const deadline = Date.now() + 8000;
  while (!await condition()) {
    if (Date.now() > deadline) throw new Error('Tempo excedido esperando os processos de teste.');
    await delay(30);
  }
}

async function exists(path) { try { await access(path); return true; } catch { return false; } }

async function cleanup(root, running) {
  if (running && running.child.exitCode === null) {
    running.child.kill('SIGTERM');
    await running.closed;
  }
  for (const name of ['backend', 'frontend']) {
    const path = join(root, name + '.pid');
    if (await exists(path)) {
      const pid = Number(await readFile(path, 'utf8'));
      try { process.kill(-pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
    }
  }
  await rm(root, { recursive: true, force: true });
}

for (const [name, options, expected] of [
  ['informa ausência da .venv', { noPython: true }, /Ambiente Python ausente/],
  ['informa dependências Python ausentes', { missingPython: ['fastapi'] }, /Dependências Python ausentes.*fastapi/],
  ['informa dependências frontend ausentes', { noFrontend: true }, /npm ci --prefix frontend/],
]) {
  await test(name, { timeout: 15000 }, async () => {
    const root = await fixture(options);
    let running;
    try {
      running = launch(root);
      assert.equal(await running.closed, 1);
      assert.match(running.output(), expected);
      assert.equal(await exists(join(root, 'backend.pid')), false);
      assert.equal(await exists(join(root, 'frontend.pid')), false);
    } finally { await cleanup(root, running); }
  });
}

for (const port of [8000, 5173]) {
  await test(`porta ${port} ocupada não inicia nenhum processo`, { timeout: 15000 }, async () => {
    const occupied = createServer();
    occupied.listen(port, '127.0.0.1');
    await once(occupied, 'listening');
    const root = await fixture();
    let running;
    try {
      running = launch(root);
      assert.equal(await running.closed, 1);
      assert.match(running.output(), new RegExp(`Porta ${port} já está em uso`));
      assert.equal(await exists(join(root, 'backend.pid')), false);
      assert.equal(await exists(join(root, 'frontend.pid')), false);
      assert.equal(occupied.listening, true);
    } finally {
      occupied.close();
      await cleanup(root, running);
    }
  });
}

for (const signal of ['SIGINT', 'SIGHUP']) {
await test(`usa backend/.venv, mostra ambos os logs e ${signal} encerra ambos`, { timeout: 15000 }, async () => {
  const root = await fixture({ backendVenv: true });
  let running;
  try {
    running = launch(root);
    await waitFor(async () => await exists(join(root, 'backend.pid')) && await exists(join(root, 'frontend.pid')));
    assert.match(running.output(), /backend\/\.venv\/bin\/python/);
    await waitFor(() => /fake backend started/.test(running.output()) && /fake frontend started/.test(running.output()));
    running.child.kill(signal);
    assert.equal(await running.closed, 0);
    for (const name of ['backend', 'frontend']) {
      const pid = Number(await readFile(join(root, name + '.pid'), 'utf8'));
      assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' });
    }
  } finally { await cleanup(root, running); }
});
}

await test('falha de um serviço encerra o outro e informa erro', { timeout: 15000 }, async () => {
  const root = await fixture({ crashFrontend: true });
  let running;
  try {
    running = launch(root);
    assert.equal(await running.closed, 1);
    assert.match(running.output(), /frontend encerrou inesperadamente/);
    const pid = Number(await readFile(join(root, 'backend.pid'), 'utf8'));
    assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' });
  } finally { await cleanup(root, running); }
});
