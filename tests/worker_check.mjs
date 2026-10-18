// Offline checks of the crowd service's rules (worker/lib.js). No Cloudflare, no network.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as lib from '../worker/lib.js';

let passed = 0;
const check = (name, fn) => { fn(); passed++; console.log('ok -', name); };
const rows = (prices) => prices.map((price, i) => ({ account: 'a' + i, price }));

check('game keys are priceKey()-shaped or refused', () => {
    assert.equal(lib.cleanGame('gta san andreas'), 'gta san andreas');
    for (const bad of ['', 'x', 'Grand Theft', 'a--b', 'a  b', "it's", 'a'.repeat(101), null, 5]) assert.equal(lib.cleanGame(bad), null, String(bad));
});
check('copies: counts 0-99 of each condition', () => {
    assert.deepEqual(lib.cleanCopies({ game: 'kuon', sealed: 0, complete: 1, loose: 2 }), { game: 'kuon', sealed: 0, complete: 1, loose: 2 });
    for (const bad of [{ game: 'kuon', sealed: -1, complete: 0, loose: 0 }, { game: 'kuon', sealed: 1.5, complete: 0, loose: 0 },
        { game: 'kuon', sealed: 100, complete: 0, loose: 0 }, { game: 'kuon', complete: 0, loose: 0 }, { game: 'Kuon!', sealed: 0, complete: 0, loose: 0 }]) assert.equal(lib.cleanCopies(bad), null);
});
check('a purchase month must be real, past and not older than two years', () => {
    const now = new Date('2026-10-17T12:00:00Z');
    assert.equal(lib.cleanMonth('2026-10', now), '2026-10');
    assert.equal(lib.cleanMonth('2024-10', now), '2024-10');
    for (const bad of ['2026-11', '2024-09', '2026-13', '2026-1', 'last month', null]) assert.equal(lib.cleanMonth(bad, now), null, String(bad));
});
check('a report needs every field from the allowed lists and a sane price', () => {
    const now = new Date('2026-10-17T12:00:00Z');
    const good = { game: 'kuon', region: 'PAL', condition: 'complete', currency: 'GBP', price: 120.456, month: '2026-09' };
    assert.deepEqual(lib.cleanReport(good, now), { ...good, price: 120.46 });
    for (const patch of [{ price: 0 }, { price: -3 }, { price: '12' }, { price: 20001 }, { region: 'JP' }, { condition: 'mint' },
        { currency: 'JPY' }, { month: '2027-01' }, { game: 'Kuon' }]) assert.equal(lib.cleanReport({ ...good, ...patch }, now), null, JSON.stringify(patch));
});
check('nothing is published for fewer than five accounts', () => {
    assert.deepEqual(lib.summarise(rows([10, 11, 12, 13])), { published: false, reporters: 4 });
    assert.equal(lib.summarise(rows([10, 11, 12, 13, 14])).published, true);
});
check('one account sending many reports still counts once', () => {
    const spam = Array.from({ length: 50 }, () => ({ account: 'same', price: 999 }));
    assert.deepEqual(lib.summarise([...spam, ...rows([10, 11, 12])]), { published: false, reporters: 4 });
});
check('a price far from the middle is held back, not counted (the 1000 euro GTA San Andreas case)', () => {
    const figure = lib.summarise(rows([20, 22, 24, 25, 26, 1000]));
    assert.equal(figure.published, true);
    assert.equal(figure.held, 1);
    assert.equal(figure.reporters, 5);
    assert.equal(figure.median, 24);
    assert.equal(figure.high, 26);
});
check('held reports are looked at again: when most accounts agree on a high price, it is published', () => {
    const figure = lib.summarise(rows([900, 950, 1000, 1000, 1100, 20]));
    assert.equal(figure.published, true);
    assert.equal(figure.median, 1000);
    assert.equal(figure.held, 1, 'now the cheap one is held');
});
check('if too many are held back, nothing is published', () => {
    const figure = lib.summarise(rows([1, 1, 1, 100, 100, 100]));
    assert.equal(figure.published, false);
});
check('owner counts need five owners and sum the copies', () => {
    const owners = (counts) => counts.map((c, i) => ({ account: 'a' + i, sealed: c[0], complete: c[1], loose: c[2] }));
    assert.equal(lib.summariseOwners(owners([[0, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]])).published, false);
    assert.equal(lib.summariseOwners(owners([[0, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0], [0, 0, 0]])).published, false, 'an account with none is not an owner');
    assert.deepEqual(lib.summariseOwners(owners([[0, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0], [0, 2, 3]])),
        { published: true, owners: 5, sealed: 1, complete: 4, loose: 4 });
});
const hash = await lib.sha256Hex('abc');
check('the saved list: title, region, condition and count only, bounded, no markup or control characters', () => {
    const good = [{ title: 'Kuon', region: 'PAL', condition: 'sealed', qty: 2 }];
    assert.deepEqual(lib.cleanList(good), good);
    assert.deepEqual(lib.cleanList([{ ...good[0], paid: 50, extra: 'x' }]), good, 'anything else is dropped, a price included');
    for (const bad of [[{ ...good[0], title: '' }], [{ ...good[0], title: '<b>x</b>' }], [{ ...good[0], title: 'a'.repeat(101) }], [{ ...good[0], region: 'JP' }],
        [{ ...good[0], condition: 'mint' }], [{ ...good[0], qty: 0 }], [{ ...good[0], qty: 100 }], [{ ...good[0], qty: 1.5 }], 'x', null,
        Array.from({ length: lib.MAX_LIST + 1 }, () => good[0])]) assert.equal(lib.cleanList(bad), null);
});
check('sha256 matches the known value', () => assert.equal(hash, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'));
check('tokens are random hex of the asked length', () => {
    const a = lib.randomToken(16), b = lib.randomToken(16);
    assert.match(a, /^[0-9a-f]{32}$/);
    assert.notEqual(a, b);
});
check('the Worker keeps no address, email or name, and never echoes an error', () => {
    const source = readFileSync(new URL('../worker/index.js', import.meta.url), 'utf8');
    assert.ok(!/console\.(log|error|warn)/.test(source), 'nothing is logged');
    assert.ok(!/INSERT[^;]*(address|email|ip)\b/i.test(source), 'no address column');
    const schema = readFileSync(new URL('../worker/schema.sql', import.meta.url), 'utf8');
    assert.ok(!/\b(email|ip_address|address|name)\b\s+(TEXT|INTEGER)/i.test(schema), 'no personal columns');
});
check('/api/wanted lists only game names: no account, no count per account, no region', () => {
    const source = readFileSync(new URL('../worker/index.js', import.meta.url), 'utf8');
    const body = source.slice(source.indexOf('async function wanted('), source.indexOf('export default'));
    assert.match(body, /SELECT game, COUNT\(DISTINCT account\) AS n FROM copies/);
    assert.match(body, /games: rows\.map\(row => row\.game\)/, 'the answer is the names alone');
    assert.ok(!/region|\.account|sealed,|complete,/.test(body.replace(/sealed \+ complete \+ loose/, '')), 'nothing else is selected or sent');
    assert.match(source, /pathname === '\/api\/wanted'/);
    assert.ok(source.indexOf("pathname === '/api/wanted'") < source.indexOf('const account = await authenticate'), 'it is read without an account, before the sign-in check');
});
const { build } = await import('../worker/bundle.mjs');
check('bundle matches lib.js and index.js (run: node worker/bundle.mjs)', () => {
    const saved = readFileSync(new URL('../worker/spindle-crowd.bundle.js', import.meta.url), 'utf8');
    assert.equal(saved, build());
    assert.ok(!/^(import|export (?!default))/m.test(saved), 'one plain file: no imports, and only export default');
});
console.log(`worker checks passed (${passed})`);
