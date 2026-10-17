// Cloudflare Worker for the dashboard's opt-in crowd data (docs/CROWD.md).
// Anonymous accounts, collection counts, purchase reports, and published figures only when enough people agree.
// Keeps no email, no address and no name. Nothing here reads or writes the repository.
import {
    cleanCopies, cleanReport, summarise, summariseOwners, sha256Hex, randomToken,
    MAX_GAMES_PER_ACCOUNT, MAX_REPORTS_PER_DAY,
} from './lib.js';

const DAY = 86400000;
const today = () => Math.floor(Date.now() / DAY);
const MAX_BODY = 200_000;
const REGISTER_PER_DAY = 5;           // per hashed network address, rotating daily
const COLLECTION_SAVES_PER_DAY = 30;  // per account

function corsHeaders(request, env) {
    const allowed = String(env.ALLOW_ORIGIN || '').split(',').map(s => s.trim()).filter(Boolean);
    const origin = request.headers.get('Origin');
    const headers = { 'Vary': 'Origin' };
    if (origin && allowed.includes(origin)) {
        headers['Access-Control-Allow-Origin'] = origin;
        headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
        headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type';
        headers['Access-Control-Max-Age'] = '86400';
    }
    return headers;
}

function reply(request, env, status, body, extra = {}) {
    return new Response(body === null ? null : JSON.stringify(body), {
        status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...corsHeaders(request, env), ...extra },
    });
}

async function readJson(request) {
    const text = await request.text();
    if (text.length > MAX_BODY) return null;
    try { return JSON.parse(text); } catch { return null; }
}

// "Authorization: Bearer <id>.<key>": the account id and its secret key. Only the key's hash is stored.
async function authenticate(request, env) {
    const header = request.headers.get('Authorization') || '';
    const match = header.match(/^Bearer ([0-9a-f]{32})\.([0-9a-f]{64})$/);
    if (!match) return null;
    const row = await env.DB.prepare('SELECT key_hash FROM accounts WHERE id = ?').bind(match[1]).first();
    if (!row) return null;
    const hash = await sha256Hex(match[2]);
    return hash === row.key_hash ? match[1] : null;
}

// Counts something against a bucket for today; false when the limit is reached.
async function allow(env, bucket, limit) {
    const day = today();
    await env.DB.prepare('INSERT INTO limits (bucket, day, n) VALUES (?, ?, 1) ON CONFLICT(bucket, day) DO UPDATE SET n = n + 1')
        .bind(bucket, day).run();
    const row = await env.DB.prepare('SELECT n FROM limits WHERE bucket = ? AND day = ?').bind(bucket, day).first();
    return row.n <= limit;
}

async function register(request, env) {
    if (!env.SALT) return reply(request, env, 503, { error: 'not configured' });
    const address = request.headers.get('CF-Connecting-IP') || 'unknown';
    const bucket = 'reg:' + await sha256Hex(`${env.SALT}|${today()}|${address}`);
    if (!await allow(env, bucket, REGISTER_PER_DAY)) return reply(request, env, 429, { error: 'too many accounts from here today' });
    const id = randomToken(16), key = randomToken(32);
    await env.DB.prepare('INSERT INTO accounts (id, key_hash, created) VALUES (?, ?, ?)').bind(id, await sha256Hex(key), today()).run();
    return reply(request, env, 201, { id, key });   // shown once: the server keeps only the key's hash
}

async function saveCollection(request, env, account) {
    const body = await readJson(request);
    if (!body || !Array.isArray(body.items) || body.items.length > MAX_GAMES_PER_ACCOUNT) return reply(request, env, 400, { error: 'bad collection' });
    const items = body.items.map(cleanCopies);
    if (items.some(item => !item)) return reply(request, env, 400, { error: 'bad collection' });
    if (!await allow(env, 'col:' + account, COLLECTION_SAVES_PER_DAY)) return reply(request, env, 429, { error: 'too many saves today' });
    // The saved list replaces the old one, so a game taken out of the collection disappears here too.
    const day = today();
    const statements = [env.DB.prepare('DELETE FROM copies WHERE account = ?').bind(account)];
    for (const { game, sealed, complete, loose } of items) {
        if (sealed + complete + loose === 0) continue;
        statements.push(env.DB.prepare('INSERT OR REPLACE INTO copies (account, game, sealed, complete, loose, updated) VALUES (?, ?, ?, ?, ?, ?)')
            .bind(account, game, sealed, complete, loose, day));
    }
    await env.DB.batch(statements);
    return reply(request, env, 200, { saved: statements.length - 1 });
}

async function addReport(request, env, account) {
    const report = cleanReport(await readJson(request));
    if (!report) return reply(request, env, 400, { error: 'bad report' });
    const day = today();
    const count = await env.DB.prepare('SELECT COUNT(*) AS n FROM reports WHERE account = ? AND created = ?').bind(account, day).first();
    if (count.n >= MAX_REPORTS_PER_DAY) return reply(request, env, 429, { error: 'too many reports today' });
    await env.DB.prepare('INSERT INTO reports (account, game, region, condition, currency, price, month, source, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
        .bind(account, report.game, report.region, report.condition, report.currency, report.price, report.month, 'other', day).run();
    return reply(request, env, 201, { ok: true });
}

async function deleteAccount(request, env, account) {
    await env.DB.batch([
        env.DB.prepare('DELETE FROM copies WHERE account = ?').bind(account),
        env.DB.prepare('DELETE FROM reports WHERE account = ?').bind(account),
        env.DB.prepare('DELETE FROM limits WHERE bucket = ?').bind('col:' + account),
        env.DB.prepare('DELETE FROM accounts WHERE id = ?').bind(account),
    ]);
    return reply(request, env, 200, { deleted: true });
}

// Figures anyone may read: only groups with enough accounts, and never one account's rows.
async function stats(request, env) {
    const cache = caches.default;
    const cacheKey = new Request(new URL('/api/stats', request.url).toString());
    let response = await cache.match(cacheKey);
    if (!response) {
        const reports = (await env.DB.prepare('SELECT game, region, condition, currency, account, price FROM reports').all()).results;
        const copies = (await env.DB.prepare('SELECT game, account, sealed, complete, loose FROM copies').all()).results;
        const groups = new Map();
        for (const r of reports) {
            const key = `${r.game}|${r.region}|${r.condition}|${r.currency}`;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push({ account: r.account, price: r.price });
        }
        const prices = {};
        for (const [key, rows] of groups) {
            const [game, region, condition, currency] = key.split('|');
            const figure = summarise(rows);
            if (!figure.published) continue;
            (prices[game] ||= []).push({ region, condition, currency, median: figure.median, low: figure.low, high: figure.high, reporters: figure.reporters });
        }
        const byGame = new Map();
        for (const c of copies) {
            if (!byGame.has(c.game)) byGame.set(c.game, []);
            byGame.get(c.game).push(c);
        }
        const owners = {};
        for (const [game, rows] of byGame) {
            const figure = summariseOwners(rows);
            if (figure.published) owners[game] = { owners: figure.owners, sealed: figure.sealed, complete: figure.complete, loose: figure.loose };
        }
        response = new Response(JSON.stringify({ generated: new Date().toISOString(), prices, owners }), {
            headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=300' },
        });
        await cache.put(cacheKey, response.clone());
    }
    const headers = new Headers(response.headers);
    for (const [name, value] of Object.entries(corsHeaders(request, env))) headers.set(name, value);
    return new Response(response.body, { status: 200, headers });
}

export default {
    async fetch(request, env) {
        const { pathname } = new URL(request.url);
        if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(request, env) });
        try {
            if (request.method === 'GET' && pathname === '/api/stats') return await stats(request, env);
            if (request.method === 'POST' && pathname === '/api/register') return await register(request, env);
            const routes = { 'PUT /api/collection': saveCollection, 'POST /api/report': addReport, 'DELETE /api/account': deleteAccount };
            const handler = routes[`${request.method} ${pathname}`];
            if (!handler) return reply(request, env, 404, { error: 'not found' });
            const account = await authenticate(request, env);
            if (!account) return reply(request, env, 401, { error: 'sign in again' });
            return await handler(request, env, account);
        } catch {
            return reply(request, env, 500, { error: 'something went wrong' });   // never echo an error: it could hold what was sent
        }
    },
};
