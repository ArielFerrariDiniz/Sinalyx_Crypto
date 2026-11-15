import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

// Usa o TypeScript já presente no projeto; não requer runner adicional.
const source = await readFile(new URL('../src/services/format.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const { decimal } = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

test('preserva quantidades e remove apenas zeros finais', () => {
  assert.equal(decimal('1234.0000123000'), '1.234,0000123');
  assert.equal(decimal('0.00000001'), '0,00000001');
});

test('não perde precisão acima do limite de Number', () => {
  assert.equal(decimal('10000000000000000.12345678'), '10.000.000.000.000.000,12345678');
  assert.equal(decimal('9999999999999999.995', 2), '10.000.000.000.000.000,00');
});

test('arredonda valores monetários com transporte para o inteiro', () => {
  assert.equal(decimal('9.995', 2), '10,00');
  assert.equal(decimal('12.344', 2), '12,34');
});

test('mostra valores positivos muito pequenos sem transformá-los em zero', () => {
  assert.equal(decimal('0.00001', 2), '< 0,01');
  assert.equal(decimal('1E-14', 8), '< 0,00000001');
  assert.equal(decimal('0', 2), '0,00');
});

test('aceita notação científica do Decimal sem conversão financeira em Number', () => {
  assert.equal(decimal('1E-8'), '0,00000001');
  assert.equal(decimal('5.6E-8', 8), '0,00000006');
  assert.equal(decimal('1.23E+6', 2), '1.230.000,00');
});
