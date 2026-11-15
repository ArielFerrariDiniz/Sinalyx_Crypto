import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/services/privacy.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const privacy = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

function fakeStorage() {
  const entries = new Map();
  return {
    entries,
    getItem: key => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, String(value)),
  };
}

test('a máscara cobre qualquer valor financeiro sem guardar o valor original', () => {
  assert.equal(privacy.financialValue('R$ 1.234,56', true), '••••••');
  assert.equal(privacy.financialValue('3,42% a.a.', true), '••••••');
  assert.equal(privacy.financialValue('0.123 BTC', true), '••••••');
  assert.equal(privacy.financialValue('0.123 BTC', false), '0.123 BTC');
});

test('persiste somente o estado visual booleano da privacidade', () => {
  const storage = fakeStorage();
  privacy.savePrivacyPreference(true, storage);

  assert.equal(privacy.readPrivacyPreference(storage), true);
  assert.deepEqual([...storage.entries], [[privacy.PRIVACY_PREFERENCE_KEY, 'true']]);

  privacy.savePrivacyPreference(false, storage);
  assert.equal(privacy.readPrivacyPreference(storage), false);
  assert.deepEqual([...storage.entries], [[privacy.PRIVACY_PREFERENCE_KEY, 'false']]);
});
