import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/services/marketView.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const view = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

function asset(symbol, pair, price, change, volume) {
  return {
    asset_id: symbol, symbol, pair, quote_asset: 'USDT', price_usdt: price,
    change_percent_24h: change, high_24h_usdt: null, low_24h_usdt: null,
    volume_usdt_24h: volume, conversion_path: [], conversion_approximate: false,
    open_time: null, close_time: null,
  };
}

const assets = [
  asset('BTC', 'BTCUSDT', '60000', '2', '100'),
  asset('ETH', 'ETHBTC', '3000', '-1', '500'),
  asset('NEW', 'NEWETH', null, null, null),
];

test('filtra por moeda e par sem diferenciar maiúsculas', () => {
  assert.deepEqual(view.filterMarketAssets(assets, 'et', ''), [assets[1]]);
  assert.deepEqual(view.filterMarketAssets(assets, '', 'usdt'), [assets[0]]);
  assert.deepEqual(view.filterMarketAssets(assets, 'b', 'btc'), [assets[0]]);
});

test('ordena indicadores numéricos e deixa indisponíveis no final', () => {
  assert.deepEqual(view.sortMarketAssets(assets, 'price_usdt', 'desc').map(item => item.symbol), ['BTC', 'ETH', 'NEW']);
  assert.deepEqual(view.sortMarketAssets(assets, 'change_percent_24h', 'asc').map(item => item.symbol), ['ETH', 'BTC', 'NEW']);
  assert.deepEqual(view.sortMarketAssets(assets, 'volume_usdt_24h', 'desc').map(item => item.symbol), ['ETH', 'BTC', 'NEW']);
});

test('ordena preços muito pequenos sem converter para ponto flutuante', () => {
  const tiny = [asset('A', 'AUSDT', '1e-50', '0', '1'), asset('B', 'BUSDT', '2e-50', '0', '1')];
  assert.deepEqual(view.sortMarketAssets(tiny, 'price_usdt', 'desc').map(item => item.symbol), ['B', 'A']);
});

test('pagina apenas o intervalo pedido sem alterar a coleção de origem', () => {
  assert.deepEqual(view.paginateMarketAssets(assets, 1, 2), [assets[2]]);
  assert.deepEqual(view.paginateMarketAssets(assets, -2, 0), [assets[0]]);
  assert.equal(assets.length, 3);
});
