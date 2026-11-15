import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/services/earnDisplay.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const earn = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

test('Earn mostra APR e recompensas sem rótulos técnicos repetitivos', () => {
  const source = {
    wallet_id: 'earn_flexible', wallet: 'Simple Earn Flexible',
    position_details: ['APR atual: 2.5% a.a. (informativo)'],
    reward_notes: [
      'Recompensas acumuladas: 0.125 ADA (informativo; não somado)',
      'Rendimento de ontem: 0.003 ADA (informativo; não somado)',
      'Airdrop de ontem: 0.001 ADA (informativo; não somado)',
    ],
  };

  assert.equal(earn.isEarnSource(source), true);
  assert.deepEqual(earn.earnDisplayValues(source), {
    apr: '2.5% a.a.', yesterday: '0.003 ADA', cumulativeRewards: '0.125 ADA',
  });
});

test('Earn exibe travessão quando a resposta não fornece os campos solicitados', () => {
  const source = {
    wallet_id: 'earn_locked', wallet: 'Simple Earn Locked',
    position_details: ['APY: 5% a.a. (informativo)', 'Prazo: 30 dias'],
    reward_notes: ['Recompensa informada: 1 TOKEN (informativo; não somado)'],
  };

  assert.deepEqual(earn.earnDisplayValues(source), {
    apr: '—', yesterday: '—', cumulativeRewards: '—',
  });
});

test('fontes Spot não são apresentadas como Earn', () => {
  assert.equal(earn.isEarnSource({ wallet_id: 'spot', wallet: 'Spot' }), false);
});
