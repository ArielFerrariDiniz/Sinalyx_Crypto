import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

async function compile(source, module = 'ESNext') {
  return ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind[module] },
  }).outputText;
}

const formatCode = await compile(await readFile(new URL('../src/services/format.ts', import.meta.url), 'utf8'));
const formatUrl = `data:text/javascript,${encodeURIComponent(formatCode)}`;
const currencyCode = await compile(await readFile(new URL('../src/services/currency.ts', import.meta.url), 'utf8'));
const linkedCurrencyCode = currencyCode.replace("from './format'", `from ${JSON.stringify(formatUrl)}`);
const currency = await import(`data:text/javascript,${encodeURIComponent(linkedCurrencyCode)}`);

test('converte valores usando multiplicação decimal exata e arredondamento a centavos', () => {
  assert.equal(currency.multiplyDecimalStrings('1661.3543570942209', '5.1234', 2), '8511.78');
  assert.equal(currency.multiplyDecimalStrings('1.005', '1', 2), '1.01');
  assert.equal(currency.multiplyDecimalStrings('1.2e3', '0.5', 2), '600.00');
});

test('formata reais, preços pequenos, valores negativos e conversão indisponível', () => {
  assert.equal(currency.formatMoney('100', 'BRL', '5.1234', 2), 'R$ 512,34');
  assert.equal(currency.formatMoney('0.0000012', 'BRL', '5.3', 8), 'R$ 0,00000636');
  assert.equal(currency.formatMoney('-2.5', 'BRL', '5', 2), '−R$ 12,50');
  assert.equal(currency.formatMoney('100', 'BRL', null, 2), null);
  assert.equal(currency.formatMoney('100', 'USD', null, 2), '100,00');
});
