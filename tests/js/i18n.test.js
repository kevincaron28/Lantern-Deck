// Every key used by the pages exists in English and French.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const I18n = require('../../web/i18n.js');
const web = path.join(__dirname, '..', '..', 'web');
const { en, fr } = I18n.dictionaries;
assert.deepEqual(Object.keys(fr).sort(), Object.keys(en).sort(), 'English and French must have the same keys');
const used = new Set();
for (const file of fs.readdirSync(web)) {
  const text = fs.readFileSync(path.join(web, file), 'utf8');
  for (const m of text.matchAll(/data-i18n(?:-placeholder)?="([^"]+)"/g)) used.add(m[1]);
  for (const m of text.matchAll(/\bt\('([a-zA-Z.]+)'/g)) used.add(m[1]);
}
const dynamic = /^(check|maison\.msg|kind\.option|kind|msg)\./;
const missing = [...used].filter(k => !(k in en) && !dynamic.test(k));
assert.deepEqual(missing, [], 'Missing translations');
for (const prefix of ['check.studio', 'check.surface', 'check.scenes', 'check.test', 'check.control'])
  for (const suffix of ['', 'Done', 'Todo']) assert.ok(prefix + suffix in en, prefix + suffix);
for (const code of ['rehearsed', 'keys_sent', 'done', 'already', 'studio_offline', 'scene_missing', 'busy', 'unconfirmed'])
  assert.ok('msg.' + code in en, code);
I18n.lang = 'fr';
assert.equal(I18n.t('phones.count', { n: 2, online: 1 }), '2 téléphones · 1 en ligne');
assert.equal(I18n.t('no.such.key'), 'no.such.key');
console.log(`i18n: ${Object.keys(en).length} keys in both languages, ${used.size} used keys covered`);
