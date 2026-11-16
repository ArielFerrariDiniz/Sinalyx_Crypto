import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/services/historyView.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const history = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

const candle = (open_time, close = String(open_time)) => ({
  open_time, open: close, high: close, low: close, close,
  volume: '1', close_time: open_time + 59_999, quote_volume: close,
  trade_count: 1,
});

test('mescla páginas ordenadas e remove candles duplicados por open_time', () => {
  const merged = history.mergeCandles([candle(200), candle(300)], [candle(100), candle(200, 'updated')]);
  assert.deepEqual(merged.map(item => item.open_time), [100, 200, 300]);
  assert.equal(merged[1].close, 'updated');
});

test('identifica apenas candles anteriores ao início já carregado', () => {
  assert.equal(history.hasNewOlderCandles([candle(200)], [candle(100)]), true);
  assert.equal(history.hasNewOlderCandles([candle(200)], [candle(200)]), false);
  assert.equal(history.hasNewOlderCandles([], [candle(100)]), true);
});
