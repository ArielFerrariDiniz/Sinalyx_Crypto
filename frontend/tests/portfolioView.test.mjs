import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/services/portfolioView.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const view = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

const wallet = (wallet_id, overrides = {}) => ({
  wallet_id, name: wallet_id, status: 'ok', asset_count: 0, total_usdt: '0', warning: null, ...overrides,
});

const asset = (symbol, overrides = {}) => ({
  asset: symbol, free: '0', locked: '0', applied: '0', liability: '0', total: '0', net_total: '0',
  price_usdt: null, value_usdt: null, conversion_path: null, sources: [], ...overrides,
});

test('esconde cartões vazios e preserva saldo sem cotação ou agregado', () => {
  const wallets = [
    wallet('spot'),
    wallet('failed', { status: 'unavailable', total_usdt: null, warning: 'Timeout' }),
    wallet('unpriced', { asset_count: 1 }),
    wallet('earn_aggregate', { total_usdt: '12.50' }),
    wallet('partial_zero', { status: 'partial', warning: 'Consulta incompleta' }),
  ];

  assert.deepEqual(view.filterWalletsWithBalance(wallets).map(item => item.wallet_id), ['unpriced', 'earn_aggregate']);
});

test('remove ativos com total zero e mantém valores mínimos e passivos', () => {
  const assets = [
    asset('ZERO'),
    asset('EXP_ZERO', { total: '0E-30', net_total: '0.000' }),
    asset('TINY', { total: '1E-30' }),
    asset('DEBT', { liability: '2', net_total: '-2' }),
  ];

  assert.deepEqual(view.filterAssetsWithBalance(assets).map(item => item.asset), ['TINY', 'DEBT']);
});

test('separa ativos sem cotação sem perder saldos positivos e exclui saldos zerados', () => {
  const assets = view.filterAssetsWithBalance([
    asset('USDT', { total: '10', net_total: '10', price_usdt: '1', value_usdt: '10' }),
    asset('ETHW', { total: '0.20811390', net_total: '0.20811390' }),
    asset('ZERO'),
  ]);
  const split = view.splitAssetsByQuoteAvailability(assets);

  assert.deepEqual(split.priced.map(item => item.asset), ['USDT']);
  assert.deepEqual(split.unpriced.map(item => item.asset), ['ETHW']);
  assert.equal(split.unpriced[0].total, '0.20811390');
});

test('detalhes da consulta preservam erros e falhas sem repetir a lista de ativos sem cotação', () => {
  const data = {
    assets: [], wallets: [
      wallet('spot'),
      wallet('earn', { status: 'unavailable', total_usdt: null, warning: 'Sem resposta da Binance' }),
      wallet('other', { status: 'unsupported', total_usdt: null, warning: null }),
    ],
    total_usdt: '0', asset_count: 0, unpriced_assets: ['ABC'], is_partial: true,
    updated_at: '2026-01-01T00:00:00Z', warnings: ['Sem resposta da Binance'], coverage_notes: ['Cobertura parcial'],
  };
  const details = view.buildQueryDetails(data, 'Falha temporária', ['Permissão adicional detectada']);

  assert.ok(details.some(item => item.includes('Falha temporária')));
  assert.ok(details.some(item => item.includes('Sem resposta da Binance')));
  assert.ok(details.some(item => item.includes('Permissão adicional detectada')));
  assert.ok(details.some(item => item.includes('não é integrada')));
  assert.ok(details.every(item => !item.includes('ABC')));
  assert.ok(details.includes('Cobertura parcial'));
});

test('estado vazio distingue carteira vazia de fonte sem confirmação', () => {
  const portfolio = (wallets) => ({
    assets: [], wallets, total_usdt: '0', asset_count: 0, unpriced_assets: [], is_partial: true,
    updated_at: '2026-01-01T00:00:00Z', warnings: [], coverage_notes: [],
  });

  assert.match(view.emptyAssetsMessage(portfolio([wallet('spot')]), []), /não retornaram posições/);
  assert.match(view.emptyAssetsMessage(portfolio([wallet('spot'), wallet('earn', {
    status: 'unavailable', total_usdt: null, warning: 'Timeout',
  })]), []), /Não foi possível confirmar/);
  assert.match(view.emptyAssetsMessage(portfolio([wallet('aggregate', { total_usdt: '3' })]), [
    wallet('aggregate', { total_usdt: '3' }),
  ]), /nenhum ativo individual foi incluído/);
});
