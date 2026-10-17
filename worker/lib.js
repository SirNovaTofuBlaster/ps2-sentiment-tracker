// Pure rules of the crowd data service (no Cloudflare calls), so Node can test them offline.
// What a Worker may accept, and how reports become published figures. See docs/CROWD.md.

export const MIN_REPORTERS = 5;       // distinct accounts needed before a figure is published
export const BAND = 3;                // a value more than 3x above or below the median is held back
export const REGIONS = ['US', 'PAL'];
export const CONDITIONS = ['sealed', 'complete', 'loose'];
export const CURRENCIES = ['USD', 'GBP', 'EUR'];
export const SOURCES = ['ebay', 'shop', 'convention', 'private', 'other'];
export const MAX_GAMES_PER_ACCOUNT = 600;
export const MAX_COPIES = 99;
export const MAX_REPORTS_PER_DAY = 20;
export const MAX_PRICE = 20000;       // in the report's own currency
export const MONTHS_BACK = 24;

// The dashboard sends priceKey(): lower case words and digits, one space between.
export function cleanGame(value) {
    const text = String(value ?? '').trim();
    return /^[a-z0-9]+(?: [a-z0-9]+)*$/.test(text) && text.length >= 2 && text.length <= 100 ? text : null;
}

const whole = (n) => Number.isInteger(n) && n >= 0 && n <= MAX_COPIES;

export function cleanCopies(body) {
    const game = cleanGame(body?.game);
    const { sealed, complete, loose } = body ?? {};
    if (!game || ![sealed, complete, loose].every(whole)) return null;
    return { game, sealed, complete, loose };
}

// months: "2026-10". Not in the future, not older than MONTHS_BACK.
export function cleanMonth(value, now = new Date()) {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(String(value))) return null;
    const [y, m] = value.split('-').map(Number);
    const index = y * 12 + (m - 1);
    const current = now.getUTCFullYear() * 12 + now.getUTCMonth();
    return index <= current && index >= current - MONTHS_BACK ? value : null;
}

export function cleanReport(body, now = new Date()) {
    const game = cleanGame(body?.game);
    const price = typeof body?.price === 'number' ? Math.round(body.price * 100) / 100 : NaN;
    const month = cleanMonth(body?.month, now);
    if (!game || !month || !Number.isFinite(price) || price <= 0 || price > MAX_PRICE) return null;
    if (!REGIONS.includes(body.region) || !CONDITIONS.includes(body.condition)
        || !CURRENCIES.includes(body.currency) || !SOURCES.includes(body.source)) return null;
    return { game, region: body.region, condition: body.condition, currency: body.currency, price, month, source: body.source };
}

export function median(values) {
    const sorted = [...values].sort((a, b) => a - b);
    const mid = sorted.length >> 1;
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

// rows: [{ account, price }] for ONE game, region, condition and currency.
// One account counts once (the median of what it reported), so nobody outweighs the rest by sending many.
// Under MIN_REPORTERS accounts nothing is published. A figure far from the middle is held back, not deleted:
// every call looks at all the rows again, so it counts as soon as the crowd agrees with it.
export function summarise(rows) {
    const byAccount = new Map();
    for (const { account, price } of rows) {
        if (!byAccount.has(account)) byAccount.set(account, []);
        byAccount.get(account).push(price);
    }
    const values = [...byAccount.values()].map(median);
    if (values.length < MIN_REPORTERS) return { published: false, reporters: values.length };
    const middle = median(values);
    const kept = values.filter(v => v <= middle * BAND && v >= middle / BAND);
    if (kept.length < MIN_REPORTERS) return { published: false, reporters: values.length, held: values.length - kept.length };
    return { published: true, reporters: kept.length, held: values.length - kept.length,
        median: Math.round(median(kept) * 100) / 100, low: Math.min(...kept), high: Math.max(...kept) };
}

// rows: [{ account, sealed, complete, loose }] for one game. Counts are published only for MIN_REPORTERS owners or more.
export function summariseOwners(rows) {
    const owners = rows.filter(r => r.sealed + r.complete + r.loose > 0);
    if (owners.length < MIN_REPORTERS) return { published: false };
    const sum = (key) => owners.reduce((total, r) => total + r[key], 0);
    return { published: true, owners: owners.length, sealed: sum('sealed'), complete: sum('complete'), loose: sum('loose') };
}

export async function sha256Hex(text) {
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, '0')).join('');
}

export function randomToken(bytes) {
    const raw = crypto.getRandomValues(new Uint8Array(bytes));
    return [...raw].map(b => b.toString(16).padStart(2, '0')).join('');
}
