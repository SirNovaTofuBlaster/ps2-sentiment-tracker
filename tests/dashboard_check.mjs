// Offline checks for the dashboard's inline script in index.html (run by tests/test_scraper.py).
//   node tests/dashboard_check.mjs                  runs the checks below
//   node tests/dashboard_check.mjs --validate FILE  prints validateConfig() verdicts for the configs in FILE
//   node tests/dashboard_check.mjs --price-keys FILE  prints priceKey() for the titles in FILE
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const root = new URL('..', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8').replace(/\r\n/g, '\n');

const script = [...read('index.html').matchAll(/<script>([\s\S]*?)<\/script>/g)]
    .map(match => match[1])
    .find(source => source.includes('function validateConfig('));
assert.ok(script, 'dashboard script with validateConfig() not found in index.html');

// Minimal browser stand-ins: one stub element per id, remembering what the script writes.
function stubElement(id = '') {
    const classes = new Set(id === 'settingsPanel' ? ['hidden'] : []);
    let html = '';
    const element = {
        id, value: '', checked: false, disabled: false, textContent: '', innerText: '',
        className: '', placeholder: '', href: '', dataset: {}, style: {}, children: [],
        classList: {
            add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c),
            toggle: (c, force) => ((force ?? !classes.has(c)) ? classes.add(c) : classes.delete(c)),
        },
        attributes: {},
        setAttribute(name, value) { this.attributes[name] = String(value); },
        getAttribute(name) { return this.attributes[name] ?? null; },
        addEventListener() {}, scrollIntoView() {}, focus() {}, reset() {}, click() {}, remove() {},
        appendChild(child) { this.children.push(child); },
    };
    // Like the DOM: assigning innerHTML replaces the element's children.
    Object.defineProperty(element, 'innerHTML', { get: () => html, set: (value) => { html = value; element.children = []; } });
    return element;
}
const elements = new Map();
// What each menu shows when the page opens: the option marked "selected", else its first.
const pageSelects = Object.fromEntries([...read('index.html').matchAll(/<select id="(\w+)"[^>]*>([\s\S]*?)<\/select>/g)]
    .map(([, id, options]) => [id, (options.match(/<option value="([^"]*)" selected>/) || options.match(/<option value="([^"]*)"/) || [])[1]]));
const defaults = { filterSelect: pageSelects.filterSelect, typeSelect: pageSelects.typeSelect, sourceShow: 'all' };
const clipboard = { text: null };
// Stand-in for Apple's podcast lookup API (the only network call the page makes itself).
const appleShows = {
    672857593: { collectionId: 672857593, collectionName: 'Retronauts', feedUrl: 'https://audioboom.com/channels/5081747.rss',
        collectionViewUrl: 'https://podcasts.apple.com/us/podcast/retronauts/id672857593?uo=4' },
    123456789: { collectionId: 123456789, collectionName: 'Test Retro Show', feedUrl: 'https://feeds.example.com/test-retro-show.rss',
        collectionViewUrl: 'https://podcasts.apple.com/us/podcast/test-retro-show/id123456789?uo=4' },
};
// Stand-in for GitHub's API (a repo "someone/ps2-sentiment-tracker"); remoteText = feeds.json as committed.
const github = { remoteText: null, sha: 'abc123', requests: [] };
const REPO_FILE = 'https://api.github.com/repos/someone/ps2-sentiment-tracker/contents/feeds.json';
const fakeFetch = async (url, options = {}) => {
    const href = String(url);
    const method = options.method || 'GET';
    github.requests.push({ href, method, headers: options.headers || {}, body: options.body ? JSON.parse(options.body) : null });
    const reply = (status, body) => ({ ok: status < 300, status, statusText: '', json: async () => body });
    if (href.startsWith('https://itunes.apple.com/lookup')) {
        const id = new URL(href).searchParams.get('id');
        return reply(200, { results: appleShows[id] ? [appleShows[id]] : [] });
    }
    if (href === 'https://api.github.com/user') return reply(200, { login: 'tester', id: 42 });
    if (href.startsWith(REPO_FILE) && method === 'PUT') return reply(200, { commit: { html_url: 'https://github.com/someone/ps2-sentiment-tracker/commit/def' } });
    if (href.startsWith(REPO_FILE) && github.remoteText !== null) {
        return reply(200, { sha: github.sha, content: Buffer.from(github.remoteText, 'utf8').toString('base64') });
    }
    return reply(404, { message: 'Not Found' });
};
const confirmAnswers = [];  // answers for the next confirm() prompts; true when empty
const addressChanges = [];  // what the page asked the address bar to show
const context = vm.createContext({
    console, Intl, URL, TextEncoder, TextDecoder, btoa, atob, setTimeout, clearTimeout,
    confirm: () => (confirmAnswers.length ? confirmAnswers.shift() : true),
    fetch: fakeFetch,
    navigator: { clipboard: { writeText: async (text) => { clipboard.text = text; } } },
    window: { addEventListener() {} },
    document: {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, Object.assign(stubElement(id), { value: defaults[id] ?? '' }));
            return elements.get(id);
        },
        createElement: () => stubElement(),
        body: { appendChild() {} },
    },
    location: { hostname: 'localhost', pathname: '/', search: '', hash: '' },
    history: { pushState(state, title, address) {
        addressChanges.push(address);
        context.location.hash = String(address).startsWith('#') ? address : '';
    } },
});
const el = (id) => context.document.getElementById(id);
vm.runInContext(script, context);
// Values cross the sandbox boundary as JSON so assertions don't trip over foreign prototypes.
const evalJson = (code) => JSON.parse(vm.runInContext(`JSON.stringify(${code})`, context));

if (process.argv[2] === '--validate') {
    context.__cases = JSON.parse(readFileSync(process.argv[3], 'utf8'));
    process.stdout.write(JSON.stringify(evalJson('__cases.map(c => validateConfig(c).length === 0)')));
    process.exit(0);
}

if (process.argv[2] === '--price-keys') {
    context.__titles = JSON.parse(readFileSync(process.argv[3], 'utf8'));
    // Thousands of titles: leave only once the whole answer has been written.
    await new Promise(done => process.stdout.write(JSON.stringify(evalJson('__titles.map(priceKey)')), done));
    process.exit(0);
}

const esc = (text) => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// The page opens on the items that name a game. Most checks below are about the whole feed,
// so they run with the menu on Everything; the check of the opening view sets it itself.
assert.equal(el('filterSelect').value, 'matched');
el('filterSelect').value = 'all';

let passed = 0;
const check = async (name, fn) => {
    await fn();
    passed++;
    console.log(`ok - ${name}`);
};

const feedsText = read('feeds.json');
context.__feeds = JSON.parse(feedsText);
context.__text = feedsText;

await check('feeds.json passes the dashboard validator', () => {
    assert.deepEqual(evalJson('validateConfig(__feeds)'), []);
});

await check('saving from the page reproduces feeds.json byte for byte', () => {
    assert.equal(evalJson('(feedConfig = __feeds, configJson())'), feedsText);
});

await check('source keys are unique and follow scraper.source_key()', () => {
    const keys = evalJson('__feeds.sources.map(sourceKey)');
    assert.equal(new Set(keys).size, keys.length);
    const sources = context.__feeds.sources;
    sources.forEach((src, i) => {
        const expected = src.type === 'youtube' ? `youtube:${src.channel_id || src.channel_url.toLowerCase()}`
            : src.type === 'reddit' ? `reddit:${src.subreddit.toLowerCase()}`
                : src.type === '4chan' ? `4chan:${src.board}` : src.url;
        assert.equal(keys[i], expected);
    });
    assert.ok(sources.some(src => src.type === '4chan') && sources.some(src => src.type === 'forum'), 'every kind of source is covered');
});

await check('weights: role default, per-source override, legacy and unknown items', () => {
    vm.runInContext(`
        feedConfig = JSON.parse(__text);
        rebuildSourceIndex();
        __collector = feedConfig.sources.find(s => s.role === 'collector');
    `, context);
    const roles = context.__feeds.roles;
    assert.equal(evalJson('effectiveWeight(__collector)'), roles.collector.weight);
    assert.equal(evalJson('(__collector.weight = 0.2, effectiveWeight(__collector))'), 0.2);
    assert.equal(evalJson('(__collector.weight = 0, effectiveWeight(__collector))'), 0);
    // Items scraped before feeds.json existed have no "feed"; r/ps2 still maps to the PS2 role.
    assert.equal(evalJson("itemWeight({ source: 'r/ps2' })"), roles.ps2.weight);
    assert.equal(evalJson("itemWeight({ source: 'Some Unknown Site' })"), 1);
    assert.equal(evalJson("effectiveWeight({ role: 'no-such-role' })"), 1);
});

await check('switched-off sources hide their items', () => {
    vm.runInContext(`
        __off = feedConfig.sources.find(s => !s.enabled);
        __on = feedConfig.sources.find(s => s.enabled);
    `, context);
    assert.equal(evalJson('isHiddenItem({ feed: sourceKey(__off), source: "x" })'), true);
    assert.equal(evalJson('isHiddenItem({ feed: sourceKey(__on), source: "x" })'), false);
    assert.equal(evalJson("isHiddenItem({ source: 'Some Unknown Site' })"), false);
});

await check('source type is read from the item or inferred for legacy items', () => {
    assert.equal(evalJson("itemType({ source_type: 'podcast', source: 'r/ps2' })"), 'podcast');
    assert.equal(evalJson("itemType({ source: 'r/ps2' })"), 'reddit');
    assert.equal(evalJson("itemType({ source: 'YouTube: IGN' })"), 'youtube');
    assert.equal(evalJson("itemType({ source: 'Podcast: Retronauts' })"), 'podcast');
    assert.equal(evalJson("itemType({ source: 'Gematsu' })"), 'news');
    assert.equal(evalJson("itemType({ source_type: 'forum', source: 'Forum: Example' })"), 'forum');
    assert.equal(evalJson("itemType({ source_type: '4chan', source: '4chan /vr/' })"), '4chan');
    assert.equal(evalJson("itemType({ source_type: 'constructor', source: 'Gematsu' })"), 'news');
});

await check('invalid configs are rejected', () => {
    const mutations = [
        "c.sources[0].url = 'not a url'",
        'c.sources.push(structuredCopy(c.sources[0]))',
        "c.sources.find(s => s.type === 'youtube').channel_id = 'UCshort'",
        "c.sources.find(s => s.type === 'reddit').subreddit = 'bad name'",
        "c.roles.press.weight = 'heavy'",
        "c.sources[0].role = 'nope'",
        'c.poll_every_hours.podcast = 0',
        "c.sources[0].enabled = 'yes'",
        "c.sources.find(s => s.type === '4chan').board = 'VR'",
        "c.sources.find(s => s.type === '4chan').board = '/vr/'",
        "delete c.sources.find(s => s.type === '4chan').board",
        "c.sources.push({ ...structuredCopy(c.sources.find(s => s.type === '4chan')), name: 'again' })",
        "c.sources.find(s => s.type === 'forum').url = 'forum.example.com/index.rss'",
        "c.poll_every_hours['4chan'] = 0",
        'c.poll_every_hours.news = 0.75',
        'c.poll_every_hours.news = 0.1',
        "c.poll_every_hours.news = '0.5'",
        'c.poll_every_hours.news = 25',
        'c.poll_every_hours.news = 1.5',
    ];
    context.structuredCopy = (value) => JSON.parse(JSON.stringify(value));
    for (const mutation of mutations) {
        const problems = evalJson(`(() => { const c = JSON.parse(__text); ${mutation}; return validateConfig(c); })()`);
        assert.ok(problems.length > 0, `not rejected: ${mutation}`);
    }
});

await check('GitHub contents API base64 helpers round-trip non-ASCII text', () => {
    assert.equal(evalJson('decodeBase64Utf8(encodeBase64Utf8(__text)) === __text'), true);
    assert.equal(evalJson("decodeBase64Utf8(encodeBase64Utf8('IGN Latinoamérica ★ 💙'))"), 'IGN Latinoamérica ★ 💙');
});

await check('dashboard renders every view and weights the sentiment average', () => {
    const feeds = context.__feeds;
    const find = (pred) => feeds.sources.find(pred);
    const press = find(s => s.enabled && s.role === 'press' && s.type === 'news');
    const collector = find(s => s.enabled && s.role === 'collector');
    const podcastSrc = find(s => s.enabled && s.type === 'podcast');
    const item = (src, sentiment, extra = {}) => ({
        headline: `${src ? src.name : 'Legacy'} headline`, source: src ? src.name : 'r/ps2', link: 'https://example.com/',
        matched_game: null, match_score: 0, is_remaster_rumor: false, sentiment, timestamp: '2026-09-30 08:00 UTC',
        ...(src ? { source_type: src.type, feed: src.type === 'youtube' ? `youtube:${src.channel_id}` : src.url } : {}),
        ...extra,
    });
    context.__items = [
        item(press, 100, { is_remaster_rumor: true }),
        item(collector, 10, { is_remaster_rumor: true, matched_game: 'Okami' }),
        item(podcastSrc, 70),
        item(null, 40),  // legacy Reddit item without "feed": maps to r/ps2 (weight 1.5)
    ];
    const anHourAgo = new Date(Date.now() - 3600e3).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
    context.__status = { [press.url]: { ok: true, latest: anHourAgo },
        [podcastSrc.url]: { ok: false, error: 'HTTP 404', failing_since: '2026-09-29 10:00 UTC', latest: null } };
    vm.runInContext(`
        feedConfig = JSON.parse(__text); baseConfigText = configJson(); rebuildSourceIndex();
        feedStatus = __status;
        allFeedData = __items;
        renderSourcesToolbar();
        refreshDashboard();
    `, context);
    // (100*1 + 10*0.5 + 70*1 + 40*1.5) / (1 + 0.5 + 1 + 1.5) = 235 / 4 = 58.75 -> 59 (unweighted: 55)
    assert.equal(el('statAvgSentiment').innerText, '59/100');
    assert.equal(el('statTotalItems').innerText, 4);
    assert.equal(el('statFeedsCount').innerText, feeds.sources.filter(s => s.enabled).length);
    // Radar: the matched PS2 game comes first even though its source weighs less.
    assert.match(el('topGamesList').innerHTML, /Okami/);
    assert.equal(el('feedTableBody').children.length, 4);
    const kinds = evalJson('SOURCE_TYPES');
    assert.deepEqual([...kinds].sort(), ['4chan', 'forum', 'news', 'podcast', 'reddit', 'youtube']);
    for (const tab of kinds) {
        vm.runInContext(`setSourceTab('${tab}')`, context);
        const html = el('sourcesView').innerHTML;
        const rows = (html.match(/<tr data-index=/g) || []).length;
        assert.equal(rows, feeds.sources.filter(s => s.type === tab).length, `${tab} rows`);
    }
    assert.match(el('sourcesView').innerHTML, /Failing: HTTP 404/);
    vm.runInContext(`setSourceTab('news')`, context);
    assert.match(el('sourcesView').innerHTML, /Active · /);
    vm.runInContext(`setSourceTab('weights')`, context);
    assert.match(el('sourcesView').innerHTML, /Role weights/);
    // Each type's clock is a menu: 15 or 30 minutes, or 1 to 24 hours, with the file's value chosen.
    const html = el('sourcesView').innerHTML;
    const menu = (type) => html.match(new RegExp(`<select data-poll="${type}"[^>]*>([\\s\\S]*?)</select>`))[1];
    const options = [...menu('podcast').matchAll(/<option value="([^"]+)"( selected)?>([^<]+)<\/option>/g)];
    assert.deepEqual(options.slice(0, 4).map(m => [m[1], m[3]]), [['0.25', '15 minutes'], ['0.5', '30 minutes'], ['1', '1 hour'], ['2', '2 hours']]);
    assert.equal(options.length, 26);
    assert.deepEqual(options.filter(m => m[2]).map(m => m[1]), [String(feeds.poll_every_hours.podcast)]);
    for (const [type, hours] of Object.entries(feeds.poll_every_hours)) {
        assert.match(menu(type), new RegExp(`<option value="${hours}" selected>`), type);
    }
    assert.match(html, /The scraper runs all the time/);
    // A type the file gives no clock is fetched hourly, and its menu says so.
    vm.runInContext("delete feedConfig.poll_every_hours.forum; setSourceTab('weights')", context);
    assert.match(el('sourcesView').innerHTML, /<select data-poll="forum"[^>]*>[\s\S]*?<option value="1" selected>1 hour<\/option>/);
    vm.runInContext("discardChanges(); setSourceTab('weights')", context);
    // Choosing 15 minutes is kept, as a number the scraper accepts; anything else is refused.
    context.__event = { target: { dataset: { poll: '4chan' }, value: '0.25' } };
    vm.runInContext('onSourcesViewChange(__event)', context);
    assert.equal(evalJson("feedConfig.poll_every_hours['4chan']"), 0.25);
    assert.deepEqual(evalJson('validateConfig(feedConfig)'), []);
    const bad = { dataset: { poll: 'news' }, value: '0.75' };
    context.__event = { target: bad };
    vm.runInContext('onSourcesViewChange(__event)', context);
    assert.equal(bad.value, feeds.poll_every_hours.news, 'the menu goes back to what it was');
    assert.equal(evalJson('feedConfig.poll_every_hours.news'), feeds.poll_every_hours.news);
    vm.runInContext('discardChanges()', context);
    assert.match(el('sourcesSummary').textContent, /sources enabled/);
    assert.equal(el('dirtyBadge').classList.contains('hidden'), true);
});

await check('switching a source off hides its items and marks the config as unsaved', () => {
    const index = context.__feeds.sources.findIndex(s => s.enabled && s.role === 'collector');
    const target = { dataset: { field: 'enabled' }, checked: false, closest: () => ({ dataset: { index: String(index) } }) };
    context.__event = { target };
    vm.runInContext('onSourcesViewChange(__event)', context);
    assert.equal(el('statTotalItems').innerText, 3);
    assert.equal(el('dirtyBadge').classList.contains('hidden'), false);
    const roleTarget = { dataset: { role: 'ps2' }, value: '3' };
    context.__event = { target: roleTarget };
    vm.runInContext('onSourcesViewChange(__event)', context);
    assert.equal(evalJson('feedConfig.roles.ps2.weight'), 3);
    // (100*1 + 70*1 + 40*3) / (1 + 1 + 3) = 290 / 5 = 58
    assert.equal(el('statAvgSentiment').innerText, '58/100');
    vm.runInContext('discardChanges()', context);
    assert.equal(el('statTotalItems').innerText, 4);
    assert.equal(el('dirtyBadge').classList.contains('hidden'), true);
});

await check('adding sources validates input and only unsaved additions can be removed', () => {
    const newId = 'UC' + 'z'.repeat(22);
    vm.runInContext(`setSourceTab('youtube')`, context);
    el('addValue').value = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';
    el('addName').value = '';
    vm.runInContext('addSource({ preventDefault() {} })', context);
    assert.match(el('sourcesMessage').innerHTML, /t a YouTube channel link/);
    el('addValue').value = `https://www.youtube.com/channel/${newId}`;
    el('addName').value = 'New Channel';
    el('addRole').value = 'retro';
    vm.runInContext('addSource({ preventDefault() {} })', context);
    assert.equal(evalJson(`feedConfig.sources.filter(s => s.channel_id === '${newId}').length`), 1);
    assert.deepEqual(evalJson('validateConfig(feedConfig)'), []);
    const html = el('sourcesView').innerHTML;
    assert.equal((html.match(/data-action="remove"/g) || []).length, 1, 'only the unsaved addition is removable');
    el('addValue').value = newId;
    el('addName').value = 'Same Channel Again';
    vm.runInContext('addSource({ preventDefault() {} })', context);
    assert.match(el('sourcesMessage').innerHTML, /already in the list/);
    vm.runInContext(`setSourceTab('reddit')`, context);
    el('addValue').value = 'https://www.reddit.com/r/ps3/';
    el('addName').value = '';
    vm.runInContext('addSource({ preventDefault() {} })', context);
    assert.equal(evalJson("feedConfig.sources.find(s => s.subreddit === 'ps3').name"), 'r/ps3');
    vm.runInContext('discardChanges()', context);
    assert.equal(evalJson("feedConfig.sources.some(s => s.subreddit === 'ps3')"), false);
});

await check('YouTube channel links and Apple Podcasts links can be pasted', async () => {
    const run = (code) => vm.runInContext(code, context);
    assert.equal(evalJson("normalizeYouTubeLink('@SomeHandle')"), 'https://www.youtube.com/@SomeHandle');
    assert.equal(evalJson("normalizeYouTubeLink('youtube.com/@LGR/videos?view=0')"), 'https://www.youtube.com/@LGR');
    assert.equal(evalJson("normalizeYouTubeLink('https://m.youtube.com/C/SomeName/featured')"), 'https://www.youtube.com/c/SomeName');
    assert.equal(evalJson("normalizeYouTubeLink('https://youtu.be/abc')"), null);

    run(`setSourceTab('youtube')`);
    el('addValue').value = 'youtube.com/@SomeNewChannel/videos';
    el('addName').value = '';
    run('addSource({ preventDefault() {} })');
    const find = "feedConfig.sources.find(s => s.channel_url === 'https://www.youtube.com/@SomeNewChannel')";
    const added = evalJson(find);
    assert.equal(added.name, '@SomeNewChannel');
    assert.equal('channel_id' in added, false, 'the scraper looks the ID up later');
    assert.equal(evalJson(`sourceKey(${find})`), 'youtube:https://www.youtube.com/@somenewchannel');
    assert.deepEqual(evalJson('validateConfig(feedConfig)'), []);
    el('addValue').value = 'https://www.youtube.com/@lgr';  // LGR is already listed (by channel ID)
    run('addSource({ preventDefault() {} })');
    assert.match(el('sourcesMessage').innerHTML, /LGR.*already in the list/);

    run(`setSourceTab('podcast')`);
    el('addValue').value = 'https://podcasts.apple.com/us/podcast/test-retro-show/id123456789?i=1000';
    el('addName').value = '';
    await run('addSource({ preventDefault() {} })');
    const show = evalJson("feedConfig.sources.find(s => s.url === 'https://feeds.example.com/test-retro-show.rss')");
    assert.equal(show.name, 'Test Retro Show');
    assert.equal(show.stats.apple_id, '123456789');
    assert.equal(show.stats.apple_url, 'https://podcasts.apple.com/us/podcast/test-retro-show/id123456789');
    assert.match(show.stats.checked, /^\d{4}-\d{2}-\d{2}$/);
    assert.deepEqual(evalJson('validateConfig(feedConfig)'), []);
    el('addValue').value = 'https://podcasts.apple.com/us/podcast/retronauts/id672857593';
    await run('addSource({ preventDefault() {} })');
    assert.match(el('sourcesMessage').innerHTML, /Retronauts.*already in the list/);
    el('addValue').value = 'https://podcasts.apple.com/us/podcast/unknown/id999999999';
    await run('addSource({ preventDefault() {} })');
    assert.match(el('sourcesMessage').innerHTML, /look that show up/);
    el('addValue').value = 'https://open.spotify.com/show/abc';
    await run('addSource({ preventDefault() {} })');
    assert.match(el('sourcesMessage').innerHTML, /Spotify/);
    assert.equal(el('addBtn').disabled, false);
    run('discardChanges()');
    assert.equal(evalJson(`${find} === undefined`), true);
});

const toggle = (index, checked) => {
    context.__event = { target: { dataset: { field: 'enabled' }, checked, closest: () => ({ dataset: { index: String(index) } }) } };
    vm.runInContext('onSourcesViewChange(__event)', context);
};
const newsIndexes = context.__feeds.sources.map((s, i) => (s.type === 'news' ? i : -1)).filter(i => i >= 0);

await check('Save without a token walks through saving on GitHub', async () => {
    context.location = { hostname: 'someone.github.io', pathname: '/ps2-sentiment-tracker/' };
    github.remoteText = evalJson('baseConfigText');  // GitHub has what this page loaded: no conflict
    toggle(newsIndexes[0], false);
    assert.equal(el('dirtyBadge').classList.contains('hidden'), false);
    await vm.runInContext('saveToGitHub()', context);
    assert.equal(clipboard.text, evalJson('configJson()'), 'the new feeds.json is on the clipboard');
    const guide = el('saveGuide');
    assert.equal(guide.classList.contains('hidden'), false);
    assert.match(guide.innerHTML, /https:\/\/github\.com\/someone\/ps2-sentiment-tracker\/edit\/main\/feeds\.json/);
    assert.match(guide.innerHTML, /Commit changes/);
    assert.match(guide.innerHTML, /Fork this repository.*Propose changes.*Create pull request/s);
    vm.runInContext('markSaved()', context);
    assert.equal(el('dirtyBadge').classList.contains('hidden'), true);
    assert.equal(guide.classList.contains('hidden'), true);
});

await check("\"I've saved it\" only counts what was copied", async () => {
    github.remoteText = evalJson('baseConfigText');
    toggle(newsIndexes[1], false);            // change A
    await vm.runInContext('saveToGitHub()', context);
    const copied = clipboard.text;
    toggle(newsIndexes[2], false);            // change B, made after copying
    vm.runInContext('markSaved()', context);
    assert.equal(evalJson('baseConfigText'), copied, 'the baseline is what was pasted on GitHub');
    assert.equal(el('dirtyBadge').classList.contains('hidden'), false, 'change B is still unsaved');
    assert.match(el('sourcesMessage').innerHTML, /still unsaved/);
    vm.runInContext('discardChanges()', context);
});

await check('saving warns when feeds.json changed on GitHub since the page loaded', async () => {
    const newer = JSON.parse(evalJson('baseConfigText'));
    newer.roles.collector.weight = 0.2;                        // someone else's (or an earlier) save
    github.remoteText = JSON.stringify(newer, null, 2) + '\n';
    toggle(newsIndexes[3], false);
    clipboard.text = null;
    confirmAnswers.push(true);                                 // OK: load the latest list first
    await vm.runInContext('saveToGitHub()', context);
    assert.equal(clipboard.text, null, 'nothing was copied');
    assert.equal(evalJson('feedConfig.roles.collector.weight'), 0.2, 'the newer list was loaded');
    assert.equal(evalJson('baseConfigText'), github.remoteText);
    assert.match(el('sourcesMessage').innerHTML, /Loaded the latest list/);
    github.remoteText = evalJson('baseConfigText');
});

await check('one-click save commits feeds.json with the no-reply identity', async () => {
    vm.runInContext("writeSettings({ repo: 'someone/ps2-sentiment-tracker', branch: 'main', token: 'tok123', remember: false })", context);
    github.requests.length = 0;
    toggle(newsIndexes[4], false);
    await vm.runInContext('saveToGitHub()', context);
    const put = github.requests.find(r => r.method === 'PUT');
    assert.ok(put, 'feeds.json was committed');
    assert.equal(put.body.sha, 'abc123');
    assert.equal(put.body.branch, 'main');
    assert.deepEqual(put.body.committer, { name: 'tester', email: '42+tester@users.noreply.github.com' });
    assert.deepEqual(put.body.author, put.body.committer);
    assert.equal(Buffer.from(put.body.content, 'base64').toString('utf8'), evalJson('configJson()'));
    assert.ok(github.requests.every(r => r.href.startsWith('https://api.github.com/') && r.headers.Authorization === 'Bearer tok123'),
        'the token only goes to api.github.com');
    assert.equal(el('dirtyBadge').classList.contains('hidden'), true);

    // A newer file on GitHub: Cancel, then Cancel again, saves nothing.
    github.remoteText = JSON.stringify({ ...JSON.parse(evalJson('baseConfigText')), version: 2 }, null, 2) + '\n';
    github.requests.length = 0;
    toggle(newsIndexes[5], false);
    confirmAnswers.push(false, false);
    await vm.runInContext('saveToGitHub()', context);
    assert.equal(github.requests.some(r => r.method === 'PUT'), false);
    assert.match(el('sourcesMessage').innerHTML, /Save cancelled/);
    vm.runInContext('discardChanges(); memorySettings = null;', context);
    context.location = { hostname: 'localhost', pathname: '/' };
    github.remoteText = null;
});

await check('pasted links are cleaned up and only unsaved additions can be removed', async () => {
    const run = (code) => vm.runInContext(code, context);
    run(`setSourceTab('news')`);
    el('addValue').value = '  https:/WWW.Example.com/feed ';
    el('addName').value = 'Example';
    run('addSource({ preventDefault() {} })');
    assert.equal(evalJson("feedConfig.sources.some(s => s.url === 'https://www.example.com/feed')"), true);
    assert.deepEqual(evalJson('validateConfig(feedConfig)'), []);

    run(`setSourceTab('youtube')`);
    el('addValue').value = 'https://www.youtube.com/@UCBerkeleyEngineeringNews';
    el('addName').value = '';
    run('addSource({ preventDefault() {} })');
    assert.equal(evalJson("feedConfig.sources.some(s => s.channel_url === 'https://www.youtube.com/@UCBerkeleyEngineeringNews')"), true,
        'a handle that starts with UC is a handle, not a channel ID');
    el('addValue').value = 'https://www.youtube.com/watch?v=abc&list=UUAAAAAAAAAAAAAAAAAAAAAAAAAA' + 'UC' + 'b'.repeat(22);
    run('addSource({ preventDefault() {} })');
    assert.match(el('sourcesMessage').innerHTML, /t a YouTube channel link/);

    run(`setSourceTab('podcast')`);
    el('addValue').value = 'https://itunes.apple.com/us/podcast/test-retro-show/id123456789';
    await run('addSource({ preventDefault() {} })');
    assert.equal(evalJson("feedConfig.sources.some(s => s.url === 'https://feeds.example.com/test-retro-show.rss')"), true);

    run(`setSourceTab('reddit')`);
    el('addValue').value = 'm.reddit.com/r/ps4/';
    run('addSource({ preventDefault() {} })');
    assert.equal(evalJson("feedConfig.sources.find(s => s.subreddit === 'ps4').name"), 'r/ps4');

    // Remove the unsaved addition with its trash button; saved sources have no such button.
    const index = evalJson("feedConfig.sources.findIndex(s => s.subreddit === 'ps4')");
    context.__click = { target: { closest: (selector) => (selector === '[data-action="remove"]'
        ? { closest: () => ({ dataset: { index: String(index) } }) } : null) } };
    run('onSourcesViewClick(__click)');
    assert.equal(evalJson("feedConfig.sources.some(s => s.subreddit === 'ps4')"), false);
    const saved = evalJson("feedConfig.sources.findIndex(s => s.subreddit === 'ps2')");
    context.__click = { target: { closest: (selector) => (selector === '[data-action="remove"]'
        ? { closest: () => ({ dataset: { index: String(saved) } }) } : null) } };
    run('onSourcesViewClick(__click)');
    assert.equal(evalJson("feedConfig.sources.some(s => s.subreddit === 'ps2')"), true, 'saved sources are never removed');
    run('discardChanges()');
});

await check('repository is detected from a GitHub Pages address', () => {
    context.location = { hostname: 'someone.github.io', pathname: '/ps2-sentiment-tracker/' };
    assert.equal(evalJson('detectRepo()'), 'someone/ps2-sentiment-tracker');
    context.location = { hostname: 'someone.github.io', pathname: '/index.html' };
    assert.equal(evalJson('detectRepo()'), 'someone/someone.github.io');
    context.location = { hostname: 'someone.github.io', pathname: '/my.repo/guide.html' };
    assert.equal(evalJson('detectRepo()'), 'someone/my.repo');
    context.location = { hostname: 'localhost', pathname: '/' };
    assert.equal(evalJson('detectRepo()'), '');
});

await check('rows name their cells so the phone layout can turn them into cards', () => {
    context.__rows = [
        { headline: 'Okami HD rumour', source: 'Eurogamer', link: 'https://e.example/1', matched_game: 'Okami', sentiment: 80, timestamp: '2026-10-01 10:00 UTC' },
        { headline: 'Nothing about a PS2 game', source: 'Eurogamer', link: 'https://e.example/2', matched_game: null, sentiment: 50, timestamp: '2026-10-01 09:00 UTC' },
    ];
    vm.runInContext('renderTable(__rows)', context);
    const [matched, unmatched] = el('feedTableBody').children.map(row => row.innerHTML);
    for (const col of ['source', 'headline', 'game', 'score', 'action']) {
        assert.match(matched, new RegExp(`<td data-col="${col}"`), `feed cell ${col}`);
    }
    assert.doesNotMatch(matched, /data-unmatched/);
    assert.match(unmatched, /<td data-col="game" data-unmatched/, 'an unmatched row says so, so a phone can drop the empty cell');

    // Source rows: every cell is named, and each statistic carries its column heading as a label.
    vm.runInContext(`setSourceTab('youtube')`, context);
    const youtube = el('sourcesView').innerHTML;
    assert.match(youtube, /<table class="sources-table /);
    for (const col of ['on', 'source', 'role', 'weight', 'stat', 'status', 'remove']) {
        assert.match(youtube, new RegExp(`<td data-col="${col}"`), `source cell ${col}`);
    }
    for (const label of ['SUBSCRIBERS', 'TOTAL VIEWS', 'LAST UPLOAD']) assert.match(youtube, new RegExp(`data-label="${label}"`));
    vm.runInContext(`setSourceTab('podcast')`, context);
    assert.match(el('sourcesView').innerHTML, /data-label="CHART US \/ UK"/);
    vm.runInContext(`setSourceTab('news')`, context);
    assert.doesNotMatch(el('sourcesView').innerHTML, /data-col="stat"/, 'news sources have no statistics columns');
});

await check('a phone gets 25 rows to a page, anything wider keeps 100', () => {
    const declaration = script.match(/^\s*const PAGE_SIZE = .*;$/m)?.[0];
    assert.ok(declaration, 'PAGE_SIZE declaration not found');
    const pageSize = (globals) => vm.runInNewContext(`${declaration} PAGE_SIZE`, globals);
    assert.equal(pageSize({}), 100, 'no matchMedia: this sandbox, or a very old browser');
    assert.equal(pageSize({ matchMedia: () => ({ matches: false }) }), 100);
    assert.equal(pageSize({ matchMedia: (query) => ({ matches: query === '(max-width: 640px)' }) }), 25);
});

await check('ranked lists show their first rows until opened, and fold away again', async () => {
    // The Demand Index shares the Tracker with the feed: five rows, at most 25.
    const demandFile = (count) => ({ window_days: 28, generated: '2026-10-06 05:41:00 UTC', games: Array.from({ length: count }, (_, n) => ({
        title: `Demand ${String(n).padStart(2, '0')}`, demand: 90 - n, views_30d: 1000, mentions: 2, trend_pct: 5 })) });
    const demand = async (count) => {
        if (count !== undefined) {
            const real = context.fetch;
            context.fetch = async () => ({ ok: true, json: async () => demandFile(count) });
            try { await vm.runInContext('loadDemand()', context); } finally { context.fetch = real; }
        }
        const html = el('demandList').innerHTML;
        return { rows: (html.match(/<li /g) || []).length, extra: (html.match(/<li class="[^"]*list-extra/g) || []).length,
            folded: el('demandList').classList.contains('is-folded'), buttonHidden: el('demandListToggle').classList.contains('hidden'),
            button: el('demandListToggle').innerHTML.replace(/ <i .*$/, '') };
    };
    assert.deepEqual(await demand(8), { rows: 8, extra: 3, folded: true, buttonHidden: false, button: 'Show 3 more' });
    assert.equal(el('demandListToggle').getAttribute('aria-expanded'), 'false');
    vm.runInContext("toggleList('demandList')", context);
    assert.deepEqual(await demand(), { rows: 8, extra: 3, folded: false, buttonHidden: false, button: 'Show fewer' });
    assert.equal(el('demandListToggle').getAttribute('aria-expanded'), 'true');
    // New data arriving does not fold a list the reader has opened.
    assert.equal((await demand(8)).folded, false);
    vm.runInContext("toggleList('demandList')", context);
    assert.deepEqual(await demand(), { rows: 8, extra: 3, folded: true, buttonHidden: false, button: 'Show 3 more' });
    assert.deepEqual(await demand(5), { rows: 5, extra: 0, folded: true, buttonHidden: true, button: 'Show 0 more' });
    assert.deepEqual(await demand(40), { rows: 25, extra: 20, folded: true, buttonHidden: false, button: 'Show 20 more' });
    assert.deepEqual(await demand(4), { rows: 4, extra: 0, folded: true, buttonHidden: true, button: 'Show 0 more' });

    // Most Mentioned Games has a page to itself: 25 rows, and every game behind the button.
    // Two items for every game, so a count of mentions cannot pass for a count of games.
    const feed = (count) => Array.from({ length: count * 2 }, (_, n) => ({
        headline: `Game ${n} news`, source: 'Eurogamer', link: 'https://e.example/', matched_game: `Game ${String(n % count).padStart(3, '0')}`,
        sentiment: 50, timestamp: '2026-10-01 10:00 UTC' }));
    const top = (count) => {
        if (count !== undefined) { context.__games = feed(count); vm.runInContext('renderTopGames(__games)', context); }
        const html = el('topGamesList').innerHTML;
        return { rows: (html.match(/<li /g) || []).length, extra: (html.match(/<li class="[^"]*list-extra/g) || []).length,
            folded: el('topGamesList').classList.contains('is-folded'), buttonHidden: el('topGamesListToggle').classList.contains('hidden'),
            button: el('topGamesListToggle').innerHTML.replace(/ <i .*$/, ''),
            badge: el('tabMentionsCount').classList.contains('hidden') ? null : el('tabMentionsCount').textContent };
    };
    assert.deepEqual(top(8), { rows: 8, extra: 0, folded: true, buttonHidden: true, button: 'Show 0 more', badge: '8' });
    assert.deepEqual(top(25), { rows: 25, extra: 0, folded: true, buttonHidden: true, button: 'Show 0 more', badge: '25' });
    assert.deepEqual(top(140), { rows: 140, extra: 115, folded: true, buttonHidden: false, button: 'Show 115 more', badge: '140' },
        'no game is left off the ranking, and the tab says how many there are');
    assert.match(el('topGamesList').innerHTML, /#140 Game 139/);
    vm.runInContext("toggleList('topGamesList')", context);
    assert.deepEqual(top(), { rows: 140, extra: 115, folded: false, buttonHidden: false, button: 'Show fewer', badge: '140' });
    vm.runInContext("toggleList('topGamesList')", context);
    assert.equal(top().folded, true);
    assert.deepEqual(top(0), { rows: 1, extra: 0, folded: true, buttonHidden: true, button: 'Show 0 more', badge: null }, 'nothing to rank: a note, no button, no number on the tab');
    assert.match(el('topGamesList').innerHTML, /Nothing to rank yet\./);

    // The stylesheet does the hiding, and stripes every second row of the lists and the feed.
    const css = read('retro.css');
    assert.match(css, /body \.is-folded > \.list-extra \{ display: none; \}/);
    assert.match(css, /body \.list-toggle:not\(\.hidden\) \{ display: inline-flex;/, 'a hidden button stays hidden');
    assert.doesNotMatch(css.replace(/@media \(hover: hover\) \{[^\n]*\n/g, ''), /\.zebra > tr:hover/,
        'row hover is only for devices that can hover');
    assert.match(css, /body \.zebra > li:nth-child\(even\), body \.zebra > tr:nth-child\(even\) \{ background-color: var\(--stripe\); \}/);
    const page = read('index.html');
    for (const id of ['demandList', 'topGamesList']) {
        assert.match(page, new RegExp(`<ol id="${id}" class="zebra"></ol>\\s*<button type="button" id="${id}Toggle" onclick="toggleList\\('${id}'\\)"`));
    }
    assert.match(page, /<ol id="pricesList" class="zebra"><\/ol>/);
    assert.doesNotMatch(page, /pricesListToggle/, 'the price list has a page to itself and shows every game');
    assert.match(page, /<tbody id="feedTableBody" class="zebra /);
});

const PRICES_NOW = Date.parse('2026-10-06T12:00:00Z');
const samplePrices = () => ({
    currencies: { US: 'USD', UK: 'GBP' },
    games: {
        'Silent Hill 2': { level: 'staple', mentions: 9, pinned: true,
            US: { checked: '2026-10-06T10:00Z', copies: 97, lowest: 120, median: 220, postage: 5.99, truncated: true },
            UK: { checked: '2026-10-06T03:00Z', copies: 47, lowest: 52.7, median: 104.69, postage: 3.29 } },
        'Gitaroo Man': { level: 'surging', mentions: 2, surging_until: '2026-10-08T09:00Z',
            US: { checked: '2026-10-06T11:50Z', copies: 1, lowest: 139.5, median: 139.5, postage: null } },
        'Jak X': { level: 'normal', mentions: 3,
            US: { checked: '2026-10-06T09:00Z', unmatched: true },
            UK: { checked: '2026-10-06T09:00Z', copies: 0, lowest: null, median: null, postage: null } },
        'Okami': { level: 'dormant', mentions: 12,
            US: { checked: '2026-10-05T20:00Z', copies: 67, lowest: 10.45, median: 34.99, postage: 6.07 } },
        '<img src=x onerror=alert(1)>': { level: 'made-up', mentions: 'lots', US: 'nonsense' },
        'Broken entry': null,
    },
});
const showPrices = (data, watchlist) => {
    context.__prices = data;
    context.__watchlist = watchlist;
    context.__now = PRICES_NOW;
    vm.runInContext("setPrices(__prices, __watchlist); renderPrices(undefined, __now, 'en-GB')", context);
    return el('pricesList').innerHTML;
};

await check('eBay prices page: every game, surging first, a line per site', () => {
    const html = showPrices(samplePrices());
    const order = [...html.matchAll(/<span class="text-cyan-300">([^<]+)/g)].map(match => match[1].trim());
    assert.deepEqual(order, ['Gitaroo Man', 'Silent Hill 2', 'Jak X', '&lt;img src=x onerror=alert(1)&gt;', 'Okami'],
        'surging first, then by mentions, quiet games last however often they were named; a broken entry is dropped');
    assert.match(el('pricesSummary').textContent, /not what anything sold for · 5 games · 1 surging$/);
    assert.equal(el('pricesEmpty').classList.contains('hidden'), true);
    assert.deepEqual([el('tabPricesCount').textContent, el('tabPricesCount').classList.contains('hidden')], ['5', false], 'the tab says how many games');

    assert.match(html, /<span class="level-tag level-surging" title="[^"]+">surging<\/span>/);
    assert.match(html, /<span class="level-tag level-dormant" title="[^"]+">quiet<\/span>/);
    assert.match(html, /<b class="ebay-median">\$220<\/b><span class="ebay-rest">median · from \$120 · 97\+ copies <span class="ebay-age" title="When eBay was last asked">· 2h ago<\/span>/);
    assert.match(html, /<b class="ebay-median">£105<\/b><span class="ebay-rest">median · from £52\.70 · 47 copies /);
    assert.match(html, /\$140<\/b><span class="ebay-rest">median · from \$140 · 1 copy <span class="ebay-age"[^>]*>· 10 min ago/);
    assert.match(html, /search needs tuning<\/span> <span class="ebay-age"/, 'unmatched is not shown as zero copies');
    assert.match(html, /<span class="ebay-note">none listed<\/span>/);
    assert.match(html, /<span class="ebay-site is-quiet"><span class="ebay-flag">UK<\/span><span class="ebay-note">not checked yet<\/span>/);
    assert.match(html, /<span class="ebay-site is-stale"><span class="ebay-flag">UK<\/span><b class="ebay-median">£105<\/b>[^\n]*?title="Not checked for longer than usual">· 9h ago/,
        'a staple is checked every 6 hours, so 9 hours is overdue');
    assert.match(html, /<span class="ebay-site"><span class="ebay-flag">US<\/span><b class="ebay-median">\$34\.99<\/b>[^\n]*?title="When eBay was last asked">· 16h ago/,
        'a quiet game is checked once a day, so 16 hours is not');
    assert.match(html, /title="Headlines naming this game in the last two weeks">9 in headlines</);
    assert.doesNotMatch(html, /<img/, 'titles are escaped');
    assert.match(html, /class="price-links"/, 'each game keeps its price lookups, eBay searches included');
    assert.doesNotMatch(html, /ebay-quotes/, 'the full lines are here already; the short form is for the Tracker');

    // No folding on this page: every game is listed, and the search box narrows them down.
    const many = { currencies: { US: '<b>', UK: 'GBP' }, games: Object.fromEntries(Array.from({ length: 8 }, (_, n) => [
        n === 3 ? 'Kingdom Hearts II' : `Game ${n}`,
        { level: 'normal', mentions: 8 - n, US: { checked: '2026-10-06T11:00Z', copies: 2, lowest: 9.5, median: 12, postage: 3 } }])) };
    const long = showPrices(many);
    const titles = (text) => [...text.matchAll(/<span class="text-cyan-300">([^<]+)/g)].map(match => match[1].trim());
    assert.equal(titles(long).length, 8);
    assert.doesNotMatch(long, /list-extra/);
    assert.match(long, /<b class="ebay-median">12\.00 &lt;b&gt;<\/b>/, 'a currency code the browser does not know is shown as text, never as markup');
    assert.doesNotMatch(long, /<b>/);

    const find = (text) => {
        el('pricesSearch').value = text;
        vm.runInContext('filterPrices()', context);
        return titles(el('pricesList').innerHTML);
    };
    assert.deepEqual(find('game 5'), ['Game 5']);
    assert.match(el('pricesSummary').textContent, / · 8 games · 1 shown$/);
    assert.deepEqual(find('  KINGDOM hearts 2 '), ['Kingdom Hearts II'], 'found however the number is written');
    assert.deepEqual(find('hearts'), ['Kingdom Hearts II']);
    for (const typing of ['k', 'kingdom h', 'Kingdom Hearts I', 'kingdom hearts ii', 'hearts ii', 'Kingdom-Hearts', 'KINGDOM  HEARTS']) {
        assert.deepEqual(find(typing), ['Kingdom Hearts II'], `"${typing}" finds it while it is still being typed`);
    }
    assert.deepEqual(find('game'), ['Game 0', 'Game 1', 'Game 2', 'Game 4', 'Game 5', 'Game 6', 'Game 7']);
    assert.deepEqual(find('zelda'), []);
    assert.deepEqual([el('pricesEmpty').classList.contains('hidden'), /^No priced game has that in its name\./.test(el('pricesEmpty').textContent)], [false, true]);
    assert.match(el('pricesSummary').textContent, / · 8 games · 0 shown$/);
    for (const nothing of ['', '   ', '&', '!?']) {
        assert.equal(find(nothing).length, 8, `"${nothing}" is not a search`);
        assert.doesNotMatch(el('pricesSummary').textContent, /shown/);
    }
    assert.equal(el('pricesEmpty').classList.contains('hidden'), true);
    assert.match(read('index.html'), /<input type="text" id="pricesSearch" oninput="filterPrices\(\)"/, 'typing in the box searches');

    // Without a price file the page says what to do instead of sitting empty.
    for (const missing of [null, {}, { games: [] }, { games: {} }]) {
        assert.equal(showPrices(missing), '', `no rows for ${JSON.stringify(missing)}`);
        assert.equal(el('pricesEmpty').classList.contains('hidden'), false);
        assert.match(el('pricesEmpty').textContent, /^No prices yet\..*Run workflow\.$/);
        assert.equal(el('tabPricesCount').classList.contains('hidden'), true);
    }
});

await check("eBay medians sit beside a game's name wherever one is shown", async () => {
    const site = (median, extra = {}) => ({ checked: '2026-10-06T11:00Z', copies: 12, lowest: median / 2, median, postage: 3, ...extra });
    const prices = samplePrices();
    Object.assign(prices.games, {
        'Shin Megami Tensei: Persona 4': { level: 'normal', mentions: 4, pinned: true, US: site(73), UK: { checked: '2026-10-06T11:00Z', unmatched: true } },
        'Kingdom Hearts II': { level: 'normal', mentions: 2, US: site(15), UK: site(8) },
        'Getaway, The': { level: 'normal', mentions: 1, UK: site(4.5) },
        'Jak and Daxter: The Precursor Legacy': { level: 'normal', mentions: 1, US: site(11) },
        '<b>Bold</b> Game': { level: 'normal', mentions: 1, US: site(9) },
    });
    const watchlist = { games: [
        { title: 'Shin Megami Tensei: Persona 4', search: 'Persona 4' }, { title: 'Okami' }, 'junk', null,
        { title: 'Not In The File', search: 'Silent Hill 2' },   // a pinned game with no figures yet takes nobody's place
    ] };
    showPrices(prices, watchlist);
    context.__now = PRICES_NOW;
    const figures = (title) => vm.runInContext(`priceFiguresHtml(${JSON.stringify(title)}, __now, 'en-GB')`, context);

    assert.equal(figures('Silent Hill 2'),
        '<span class="ebay-quotes"><span class="ebay-quotes-label">eBay median</span>'
        + '<a class="ebay-quote" href="https://www.ebay.com/sch/i.html?_nkw=Silent%20Hill%202%20ps2" target="_blank" rel="noopener noreferrer"'
        + ' title="Median asking price of 97+ used copies on eBay US, cheapest $120, checked 2h ago. Opens eBay&#39;s search for this game.">'
        + '<span class="ebay-flag">US</span><b>$220</b></a>'
        + '<a class="ebay-quote is-stale" href="https://www.ebay.co.uk/sch/i.html?_nkw=Silent%20Hill%202%20ps2" target="_blank" rel="noopener noreferrer"'
        + ' title="Median asking price of 47 used copies on eBay UK, cheapest £52.70, checked 9h ago (longer ago than usual). Opens eBay&#39;s search for this game.">'
        + '<span class="ebay-flag">UK</span><b>£105</b></a></span>');

    // The feed's spelling finds the price file's.
    const sites = (title) => [...figures(title).matchAll(/<span class="ebay-flag">(\w+)<\/span><b>([^<]+)<\/b>/g)].map(match => `${match[1]} ${match[2]}`);
    assert.deepEqual(sites('SILENT HILL 2'), ['US $220', 'UK £105']);
    assert.deepEqual(sites('Persona 4'), ['US $73.00'], "a pinned game's search words name it too; a site with nothing counted is left out");
    assert.deepEqual(sites('Shin Megami Tensei: Persona 4'), ['US $73.00']);
    assert.deepEqual(sites('Kingdom Hearts 2'), ['US $15.00', 'UK £8.00']);
    assert.deepEqual(sites('The Getaway'), ['UK £4.50']);
    assert.deepEqual(sites('Jak & Daxter: The Precursor Legacy'), ['US $11.00']);
    assert.deepEqual(sites('Gitaroo Man'), ['US $140'], 'one copy: the wording follows');
    assert.match(figures('Gitaroo Man'), /of 1 used copy on eBay US, cheapest \$140, checked 10 min ago\./);
    assert.deepEqual(sites('Okami'), ['US $34.99']);
    assert.doesNotMatch(figures('Okami'), /is-stale|longer ago/, 'a quiet game is checked once a day, so 16 hours is not overdue');
    // Nothing is shown rather than something misleading.
    for (const title of ['Jak X', 'Silent Hill', 'Silent Hill 3', 'Black', 'Not In The File', '', null, undefined, 'constructor', '<img src=x onerror=alert(1)>']) {
        assert.equal(figures(title), '', `no figures for ${JSON.stringify(title)}`);
    }
    const hostile = figures('<b>Bold</b> Game');
    assert.match(hostile, /_nkw=%3Cb%3EBold%3C%2Fb%3E%20Game%20ps2"/);
    assert.doesNotMatch(hostile, /<b>Bold/);
    // Nothing from the price file reaches the page as markup either: not in the figure, not in its tooltip.
    showPrices({ ...prices, currencies: { US: '"><img src=x onerror=alert(1)>', UK: 'GBP' } }, watchlist);
    const odd = figures('Kingdom Hearts II');
    assert.match(odd, /<b>15\.00 &quot;&gt;&lt;img src=x onerror=alert\(1\)&gt;<\/b>/);
    assert.match(odd, /cheapest 7\.50 &quot;&gt;&lt;img/);
    assert.doesNotMatch(odd, /<img|"">/);
    showPrices(prices, watchlist);

    // The places a game's name appears: Most Mentioned Games, the table, the Demand Index
    // and the games named in the last day.
    const item = (game) => ({ headline: `${game} news`, source: 'Eurogamer', link: 'https://e.example/', matched_game: game, sentiment: 50, timestamp: '2026-10-01 10:00 UTC' });
    context.__games = [item('Persona 4'), item('Persona 4'), item('Black'), { ...item(''), matched_game: null }];
    vm.runInContext('renderTopGames(__games)', context);
    const rows = el('topGamesList').innerHTML.split('<li ').slice(1);
    assert.equal(rows.length, 2);
    assert.match(rows[0], /#1 Persona 4[\s\S]*<span class="ebay-quotes">[\s\S]*<span class="price-links"/, 'medians first, then the lookup chips');
    assert.match(rows[1], /#2 Black/);
    assert.doesNotMatch(rows[1], /ebay-quotes/, 'a game that is not priced keeps its chips and nothing else');
    assert.match(rows[1], /class="price-links"/);

    vm.runInContext('renderTable(__games)', context);
    const cells = el('feedTableBody').children.map(row => row.innerHTML.match(/<td data-col="game"[\s\S]*?<\/td>/)[0]);
    assert.deepEqual(cells.map(cell => /ebay-quotes/.test(cell)), [true, true, false, false]);
    assert.match(cells[0], />Persona 4<span class="ebay-quotes">/);

    const real = context.fetch;
    context.fetch = async () => ({ ok: true, json: async () => ({ window_days: 30, generated: '2026-10-06 05:41:00 UTC', games: [
        { title: 'Kingdom Hearts II', demand: 80, views_30d: 1000, mentions: 2, trend_pct: 5 },
        { title: 'Black', demand: 60, views_30d: 900, mentions: 8, trend_pct: null }] }) });
    try { await vm.runInContext('loadDemand()', context); } finally { context.fetch = real; }
    const demand = el('demandList').innerHTML.split('<li ').slice(1);
    assert.deepEqual(demand.map(row => /ebay-quotes/.test(row)), [true, false]);

    const noon = Date.parse('2026-10-01T12:00:00Z');
    vm.runInContext(`renderRecentGames(__games, ${noon})`, context);
    const named = el('todayList').innerHTML.split('<li ').slice(1);
    assert.deepEqual(named.map(row => [/>(?:Persona 4|Black)<\/button>/.exec(row)?.[0], /ebay-quotes/.test(row)]),
        [['>Persona 4</button>', true], ['>Black</button>', false]]);
    assert.match(named[0], /<span class="ebay-quotes">[\s\S]*<span class="price-links"/);

    // No price file: every list looks as it did before prices existed.
    showPrices(null);
    vm.runInContext(`renderTopGames(__games); renderTable(__games); renderRecentGames(__games, ${noon})`, context);
    assert.doesNotMatch(el('topGamesList').innerHTML + el('todayList').innerHTML + el('feedTableBody').children.map(row => row.innerHTML).join(''), /ebay-quote/);
    assert.equal(figures('Silent Hill 2'), '');

    const css = read('retro.css');
    assert.match(css, /body \.ebay-quote\.is-stale b \{ opacity: \.5; \}/);
});

await check('eBay prices: money and ages read naturally', () => {
    const money = (value, currency) => evalJson(`money(${JSON.stringify(value)}, '${currency}', 'en-GB')`);
    assert.equal(money(220, 'USD'), '$220', 'the site is named beside every figure, so no "US$"');
    assert.equal(money(1299.99, 'USD'), '$1,300');
    assert.equal(money(99.99, 'GBP'), '£99.99');
    assert.equal(money(52.7, 'GBP'), '£52.70');
    assert.equal(money(null, 'GBP'), '');
    assert.equal(evalJson("money('12', 'GBP', 'en-GB')"), '');
    assert.equal(evalJson("money(12, 'GBP', 'en-US')"), '£12.00');
    assert.equal(evalJson("money(12, 'USD', 'en-US')"), '$12.00');

    const now = Date.parse('2026-10-06T12:00:00Z');
    const age = (stamp, hours) => evalJson(`priceAge(${JSON.stringify(stamp)}, ${now}${hours ? `, ${hours}` : ''})`);
    assert.deepEqual(age('2026-10-06T12:00Z'), { text: '1 min ago', stale: false });
    assert.deepEqual(age('2026-10-06T11:15Z'), { text: '45 min ago', stale: false });
    assert.deepEqual(age('2026-10-06T04:00Z'), { text: '8h ago', stale: false });
    assert.deepEqual(age('2026-10-06T03:59Z'), { text: '8h ago', stale: true });
    assert.deepEqual(age('2026-10-06T08:59Z', 3), { text: '3h ago', stale: true }, 'a surging game is overdue sooner');
    assert.deepEqual(age('2026-10-05T07:00Z', 30), { text: '29h ago', stale: false }, 'a quiet game is given a day');
    assert.deepEqual(age('2026-10-03T12:00Z'), { text: '3d ago', stale: true });
    assert.deepEqual(evalJson('Object.fromEntries(Object.entries(LEVELS).map(([name, level]) => [name, level.stale]))'),
        { surging: 3, staple: 8, normal: 8, dormant: 30 });
    assert.deepEqual(age('not a time'), { text: '', stale: true });
    assert.deepEqual(age('2026-10-06T13:00Z'), { text: '1 min ago', stale: false }, 'a clock that is slightly off does not show a negative age');
});

await check('one name for a game however it is spelt, the way ebay_prices.py does it', () => {
    // tests/test_scraper.py compares priceKey() with ebay_prices.search_terms() on the whole library.
    const key = (title) => evalJson(`priceKey(${JSON.stringify(title)})`);
    assert.equal(key('Kingdom Hearts II'), 'kingdom hearts 2');
    assert.equal(key('Jak & Daxter: The Precursor Legacy'), 'jak daxter the precursor legacy');
    assert.equal(key("Godfather, The: Collector's Edition"), 'godfather collectors edition');
    assert.equal(key('The Getaway'), 'getaway');
    assert.equal(key('Getaway, The'), 'getaway');
    assert.equal(key('The'), 'the', 'a title that is only an article keeps it');
    assert.equal(key('Ōkami™ (PS2)'), 'okami ps2');
    assert.equal(key('Director’s Cut'), 'directors cut');
    assert.equal(key('Final Fantasy X-2'), 'final fantasy x 2');
    assert.equal(key('A.I. Wars'), 'a i wars', '"A." is not the article "A"');
    assert.equal(key('constructor toString II'), 'constructor tostring 2', 'ordinary words that are also JavaScript names');
    assert.deepEqual([key(''), key(null), key(undefined), key(42)], ['', '', '', '42']);
});

await check('prices are read from the site itself, with no token, before the lists are drawn', async () => {
    github.requests.length = 0;
    await vm.runInContext('loadPrices()', context);
    assert.deepEqual(github.requests.map(r => [r.href, r.method, Object.keys(r.headers)]),
        [['data/prices/latest.json', 'GET', []], ['ebay_watchlist.json', 'GET', []]]);
    assert.equal(el('pricesEmpty').classList.contains('hidden'), false, 'the file is not there in this sandbox');
    assert.match(el('pricesEmpty').textContent, /^No prices yet\./);

    const real = context.fetch;
    const warn = context.console.warn;
    const warnings = [];
    context.console.warn = (...parts) => warnings.push(parts[0]);
    const good = {
        'data/prices/latest.json': { games: { 'Shin Megami Tensei: Persona 4': { level: 'normal', mentions: 1,
            US: { checked: '2026-10-06T11:00Z', copies: 2, lowest: 9, median: 12 } } } },
        'ebay_watchlist.json': { games: [{ title: 'Shin Megami Tensei: Persona 4', search: 'Persona 4' }] },
    };
    // What the site answers for each file: a body (200), a status code, 'drop' (no connection) or 'garbage' (not JSON).
    let answers = {};
    context.fetch = async (path) => {
        const answer = path in answers ? answers[path] : 404;
        if (answer === 'drop') throw new TypeError('Failed to fetch');
        if (answer === 'garbage') return { ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token'); } };
        if (typeof answer === 'number') return { ok: false, status: answer, json: async () => ({}) };
        return { ok: true, status: 200, json: async () => answer };
    };
    const load = async (next) => { answers = next; await vm.runInContext('loadPrices()', context); };
    const figure = (title) => vm.runInContext(`priceFiguresHtml(${JSON.stringify(title)}) !== ''`, context);
    const state = () => ({ short: figure('Persona 4'), full: figure('Shin Megami Tensei: Persona 4'),
        rows: (el('pricesList').innerHTML.match(/<li /g) || []).length, note: el('pricesEmpty').classList.contains('hidden') ? '' : el('pricesEmpty').textContent.slice(0, 13) });
    const SHOWN = { short: true, full: true, rows: 1, note: '' };
    try {
        await load(good);
        assert.deepEqual(state(), SHOWN, 'a good file is shown, and the watchlist ties the short name to it');

        // A hiccup on REFRESH keeps what is on screen: prices, and the names that find them.
        for (const trouble of [503, 500, 'drop', 'garbage']) {
            await load({ ...good, 'data/prices/latest.json': trouble });
            assert.deepEqual(state(), SHOWN, `prices survive "${trouble}"`);
            await load({ ...good, 'ebay_watchlist.json': trouble });
            assert.deepEqual(state(), SHOWN, `the watchlist survives "${trouble}"`);
        }
        // The watchlist is a help, not a requirement: without it the library title still finds the price.
        await load({ 'data/prices/latest.json': good['data/prices/latest.json'] });
        assert.deepEqual(state(), { ...SHOWN, short: false });
        // The price file really gone: say so, and say what to do.
        await load({});
        assert.deepEqual(state(), { short: false, full: false, rows: 0, note: 'No prices yet' });

        // Nothing loaded yet and the file cannot be read: that is not "no prices yet".
        for (const trouble of [503, 'drop', 'garbage']) {
            await load({ 'data/prices/latest.json': trouble });
            assert.deepEqual(state(), { short: false, full: false, rows: 0, note: 'The price fil' }, `"${trouble}" with nothing loaded`);
            assert.match(el('pricesEmpty').textContent, /Press REFRESH to try again\./);
        }
        await load(good);
        assert.deepEqual(state(), SHOWN, 'and it recovers on the next try');
        assert.deepEqual(warnings, []);

        // A file the page cannot draw must not stop the rest of the page.
        context.__realRows = vm.runInContext('priceRows', context);
        vm.runInContext("priceRows = () => { throw new Error('boom'); }", context);
        await load(good);
        assert.deepEqual(warnings, ['Could not show data/prices/latest.json.']);
        assert.equal(figure('Shin Megami Tensei: Persona 4'), false);
    } finally {
        vm.runInContext('if (typeof __realRows === "function") priceRows = __realRows', context);
        context.fetch = real;
        context.console.warn = warn;
    }
    await vm.runInContext('loadPrices()', context);
    assert.match(el('pricesEmpty').textContent, /^No prices yet\./);

    assert.match(read('index.html'), /await loadPrices\(\);\s*await loadDemand\(\);\s*refreshDashboard\(\);/,
        'prices are loaded before the lists that show them');
});

await check('three pages in one: Tracker, Most mentioned and eBay prices', () => {
    const views = { dashboard: ['viewDashboard', 'tabDashboard'], mentions: ['viewMentions', 'tabMentions'], prices: ['viewPrices', 'tabPrices'] };
    // Which page is on screen, and which tab says so. Exactly one of each, always.
    const shown = () => {
        const open = Object.keys(views).filter(name => !el(views[name][0]).classList.contains('hidden'));
        const lit = Object.keys(views).filter(name => el(views[name][1]).classList.contains('is-active'));
        assert.deepEqual(open, lit, 'the lit tab is the page on screen');
        assert.equal(open.length, 1, 'one page at a time');
        return open[0];
    };
    addressChanges.length = 0;
    context.location.hash = '';
    const show = (name) => { vm.runInContext(`showView(${JSON.stringify(name)})`, context); return shown(); };
    const selected = () => Object.keys(views).map(name => el(views[name][1]).getAttribute('aria-selected')).join(' ');
    assert.equal(show('prices'), 'prices');
    assert.equal(selected(), 'false false true', 'a screen reader hears which tab is open');
    assert.equal(show('prices'), 'prices');
    assert.equal(show('mentions'), 'mentions');
    assert.equal(selected(), 'false true false');
    assert.equal(show('dashboard'), 'dashboard');
    assert.equal(selected(), 'true false false');
    assert.equal(show('dashboard'), 'dashboard');
    assert.deepEqual(addressChanges, ['#prices', '#mentions', '/'],
        'each change of page is one new entry in the history, so Back returns to the last page and the address can be bookmarked');
    for (const name of ['nonsense', 'constructor', 'toString', '', null]) assert.equal(show(name), 'dashboard', `"${name}" is not a page`);
    assert.deepEqual(addressChanges, ['#prices', '#mentions', '/'], 'staying on a page adds nothing to the history');
    // Leaving a part of the Tracker that the address names ("#sourcesSection") by its own tab clears the name.
    context.location.hash = '#sourcesSection';
    assert.equal(show('dashboard'), 'dashboard');
    assert.deepEqual(addressChanges, ['#prices', '#mentions', '/', '/']);

    // Arriving with an address, or following a link such as the header's "Sources".
    addressChanges.length = 0;
    let scrolled = 0;
    el('sourcesSection').scrollIntoView = () => { scrolled++; };
    const arrive = (hash) => { context.location.hash = hash; vm.runInContext('showViewFromAddress()', context); return shown(); };
    assert.equal(arrive('#prices'), 'prices');
    assert.equal(arrive('#sourcesSection'), 'dashboard', 'a link into the Tracker leaves the other pages');
    assert.equal(scrolled, 1, 'and goes to the part it names');
    assert.equal(arrive('#mentions'), 'mentions');
    assert.equal(arrive('#sourcesSection'), 'dashboard');
    assert.equal(scrolled, 2);
    assert.equal(arrive('#prices'), 'prices');
    for (const hash of ['', '#', '#dashboard', '#constructor', '#__proto__']) assert.equal(arrive(hash), 'dashboard', `"${hash}" opens the Tracker`);
    assert.deepEqual(addressChanges, [], 'reading the address never rewrites it');
    context.location.hash = '';

    const page = read('index.html');
    const at = (text) => { const index = page.indexOf(text); assert.notEqual(index, -1, text); assert.equal(page.indexOf(text, index + 1), -1, `${text} appears once`); return index; };
    const order = ['id="tabDashboard"', 'id="tabMentions"', 'id="tabPrices"',
        '<div id="viewDashboard" role="tabpanel" aria-labelledby="tabDashboard" class="space-y-8">', 'id="demandSection"', 'id="feedSection"', 'id="sourcesSection"',
        '<div id="viewMentions" role="tabpanel" aria-labelledby="tabMentions" class="hidden ', 'id="topGamesSection"',
        '<div id="viewPrices" role="tabpanel" aria-labelledby="tabPrices" class="hidden ', 'id="pricesSection"', '</main>'].map(at);
    assert.deepEqual(order, [...order].sort((a, b) => a - b), 'each list is on its own page, after everything on the Tracker');
    for (const [name, [panel, tab]] of Object.entries(views)) {
        assert.match(page, new RegExp(`id="${tab}" role="tab" aria-selected="${name === 'dashboard'}" aria-controls="${panel}" onclick="showView\\('${name}'\\)"`));
    }
    assert.match(page, /showViewFromAddress\(\);\s*window\.addEventListener\('hashchange', showViewFromAddress\);\s*window\.addEventListener\('popstate', showViewFromAddress\);/,
        'links, Back and Forward all go through the address');
    assert.match(page, /fetchSentimentData\(\)\.finally\(showViewFromAddress\);/, 'a part named in the address is found again once the page has its content');

    // Every element the script asks for by name exists in the page. A missing one would stop
    // whatever was being drawn, which a sandbox that invents elements cannot notice.
    const asked = new Set([...script.matchAll(/getElementById\('([A-Za-z][\w-]*)'\)/g)].map(match => match[1]));
    const missing = [...asked].filter(id => !page.includes(`id="${id}"`));
    assert.deepEqual(missing, []);
    assert.ok(asked.size > 40);
    assert.match(read('retro.css'), /body \.view-tab\.is-active \{[^}]*border-bottom-color: var\(--red\)/);
});

await check('the item count says how far back it goes', () => {
    const now = Date.parse('2026-10-07T09:00:00Z');
    const label = (stamps) => { context.__items = stamps.map(timestamp => ({ timestamp })); return vm.runInContext(`itemsLabel(__items, ${now})`, context); };
    assert.equal(label(['2026-10-07 08:00 UTC', '2026-09-28 01:01 UTC', '2026-10-01 10:00 UTC']), 'Items · 9 days', 'from the oldest item, wherever it is in the list');
    assert.equal(label(['2026-09-23 09:00 UTC']), 'Items · 14 days');
    assert.equal(label(['2026-09-23 18:00 UTC']), 'Items · 14 days', '13 days and 15 hours is nearer 14 than 13');
    assert.equal(label(['2026-09-24 00:00 UTC']), 'Items · 13 days');
    assert.equal(label(['2026-10-07 08:00 UTC']), 'Items · 1 day');
    assert.equal(label(['2026-10-06 03:00 UTC']), 'Items · 1 day');
    assert.equal(label([]), 'Items scraped');
    assert.equal(label(['not a time', undefined]), 'Items scraped');
    assert.equal(label(['2026-10-09 08:00 UTC']), 'Items scraped', 'a clock that is off never gives a negative span');
    assert.equal(label(['not a time', '2026-10-04 09:00 UTC']), 'Items · 3 days');

    // The tile itself: the count is what is on screen, the span is the whole feed's.
    const span = () => `Items · ${Math.max(1, Math.round((Date.now() - Date.parse('2026-06-06T10:15:00Z')) / 86400000))} days`;
    context.__feed = [
        { headline: 'A', source: 'Eurogamer', link: 'https://e.example/a', matched_game: null, sentiment: 50, timestamp: '2026-06-06 11:30 UTC' },
        { headline: 'B', source: 'Eurogamer', link: 'https://e.example/b', matched_game: null, sentiment: 50, timestamp: '2026-06-06 10:15 UTC' }];
    const before = span();
    vm.runInContext('allFeedData = __feed; refreshDashboard()', context);
    assert.equal(el('statTotalItems').innerText, 2);
    assert.ok([before, span()].includes(el('statTotalLabel').textContent), el('statTotalLabel').textContent);
    // The stand-in data shown before the first scrape is not a window of anything.
    vm.runInContext('allFeedData = fallbackData.items; refreshDashboard()', context);
    assert.equal(el('statTotalLabel').textContent, 'Items scraped');
    assert.match(read('index.html'), /<div id="statTotalLabel" class="stat-label">Items scraped<\/div>\s*<div id="statTotalItems" class="stat-value">0<\/div>/);
});

await check('forums and 4chan boards: their rows, their weight and adding one', () => {
    const feeds = context.__feeds;
    const press = feeds.sources.find(src => src.enabled && src.role === 'press' && src.type === 'news');
    const forum = feeds.sources.find(src => src.type === 'forum');
    const row = (extra) => ({ link: 'https://example.com/', matched_game: null, is_remaster_rumor: false, sentiment: 50, timestamp: '2026-10-07 08:00 UTC', ...extra });
    context.__items = [
        row({ headline: 'Press headline', source: press.name, source_type: 'news', feed: press.url, sentiment: 90 }),
        row({ headline: 'Ico appreciation thread', source: `Forum: ${forum.name}`, source_type: 'forum', feed: forum.url, sentiment: 70, matched_game: 'Ico',
            link: 'https://forum.example/threads/ico.1/' }),
        // As the scraper writes it: a thread is not scored, so its sentiment is null.
        row({ headline: 'Thread on /vr/ naming Okami', source: '4chan /vr/', source_type: '4chan', feed: '4chan:vr', matched_game: 'Okami',
            link: 'https://boards.4chan.org/vr/thread/101', sentiment: null }),
    ];
    vm.runInContext(`
        feedConfig = JSON.parse(__text); baseConfigText = configJson(); rebuildSourceIndex(); unsavedAdditions.clear();
        allFeedData = __items;
        refreshDashboard();
    `, context);
    const rows = () => el('feedTableBody').children.map(child => child.innerHTML);

    // A board's rows count for the games they name and for nothing else: the role's weight is 0,
    // so the mood score is the press item and the forum thread only. (90*1 + 70*1) / 2 = 80
    assert.equal(feeds.roles.anonymous.weight, 0);
    assert.ok(feeds.sources.filter(src => src.type === '4chan').every(src => src.role === 'anonymous' && !('weight' in src)));
    assert.equal(el('statAvgSentiment').innerText, '80/100');
    assert.equal(el('statTotalItems').innerText, 3);
    assert.match(el('topGamesList').innerHTML, /#1 Ico[\s\S]*#2 Okami/, 'both count as mentions');

    const [, forumRow, boardRow] = rows();
    assert.match(forumRow, /fa-solid fa-comments[^>]*title="Forums"><\/i>Forum: /);
    assert.match(forumRow, /href="https:\/\/forum\.example\/threads\/ico\.1\/"[^>]*>\s*Thread /);
    // 4chan asks that it be named as the source and linked to.
    assert.match(boardRow, /fa-solid fa-user-secret[^>]*title="4chan"><\/i>4chan \/vr\//);
    assert.match(boardRow, /Thread on \/vr\/ naming Okami/);
    assert.match(boardRow, /href="https:\/\/boards\.4chan\.org\/vr\/thread\/101"[^>]*>\s*Thread /);
    assert.match(boardRow, /title="Source weight in the sentiment average">&times;0<\/span>/);
    assert.match(boardRow, /<td data-col="score"[^>]*><div class="score-value[^"]*" title="Not scored: [^"]+">&ndash;<\/div>\s*<\/td>/, 'no mood is shown for a thread');
    assert.match(forumRow, /<div class="score-value font-mono-custom">70<\/div>/);
    // A thread has no mood score at all, so no weight can bring it into the average as a
    // neutral 50: not a weight on the role, not one on the board, and not a board the list has lost.
    const mood = (change) => {
        vm.runInContext(`${change}; rebuildSourceIndex(); refreshDashboard()`, context);
        return el('statAvgSentiment').innerText;
    };
    assert.equal(mood('feedConfig.roles.anonymous.weight = 5'), '80/100');
    assert.equal(mood("feedConfig.roles.anonymous.weight = 0; feedConfig.sources.find(s => s.board === 'vr').weight = 10"), '80/100');
    assert.equal(mood("feedConfig.sources = feedConfig.sources.filter(s => s.board !== 'vr')"), '80/100');
    // ...while a weight on the forum does what it says. (90*1 + 70*3) / 4 = 75
    assert.equal(mood(`feedConfig = JSON.parse(__text); feedConfig.sources.find(s => s.type === 'forum').weight = 3`), '75/100');
    assert.equal(mood('feedConfig = JSON.parse(__text)'), '80/100');

    // The feed can be narrowed to either kind.
    const only = (kind) => { el('typeSelect').value = kind; vm.runInContext('filterFeedItems()', context); return rows().length; };
    assert.deepEqual([only('4chan'), only('forum'), only('news'), only('all')], [1, 1, 1, 3]);
    const page = read('index.html');
    assert.match(page, /<option value="forum">Forums<\/option>\s*<option value="4chan">4chan<\/option>/);

    // Sources & Weights: a tab for each, with the board's own page as its link.
    vm.runInContext("setSourceTab('4chan')", context);
    let html = el('sourcesView').innerHTML;
    assert.equal((html.match(/<tr data-index=/g) || []).length, feeds.sources.filter(src => src.type === '4chan').length);
    assert.match(html, /<a href="https:\/\/boards\.4chan\.org\/vr\/"[^>]*>\/vr\/ - Retro Games<\/a>/);
    assert.doesNotMatch(html, /data-field="weight"/, 'a board has no weight to set');
    assert.equal((html.match(/<td data-col="weight"[^>]*><span[^>]*title="Not scored, [^"]+">&ndash;<\/span><\/td>/g) || []).length,
        feeds.sources.filter(src => src.type === '4chan').length);
    assert.match(el('addHint').textContent, /^Add to 4chan: only the names of the PS2 games/);
    const add = (value, name = '') => {
        el('addValue').value = value; el('addName').value = name;
        vm.runInContext('addSource({ preventDefault() {} })', context);
        return el('sourcesMessage').innerHTML;
    };
    assert.match(add('vp'), /^Added \/vp\/\./);
    assert.deepEqual(evalJson("feedConfig.sources.find(s => s.board === 'vp')"),
        { type: '4chan', name: '/vp/', board: 'vp', group: evalJson("feedConfig.sources.find(s => s.type === '4chan').group"), role: 'anonymous', enabled: true });
    assert.match(add(' /Tg/ ', 'Traditional Games'), /^Added Traditional Games\./);
    assert.equal(evalJson("feedConfig.sources.find(s => s.board === 'tg').name"), 'Traditional Games');
    assert.match(add('https://boards.4chan.org/vrpg/catalog'), /is already in the list/);
    assert.match(add('boards.4channel.org/vst/thread/123'), /is already in the list/);
    for (const junk of ['not a board!', 'https://example.com/vr/', 'toolongname', 'v r', '.']) {
        assert.match(add(junk), /Enter the short name of a board/, junk);
    }
    assert.deepEqual(evalJson("feedConfig.sources.filter(s => s.type === '4chan').map(s => s.board).slice(-2)"), ['vp', 'tg'], 'new boards join the other boards');

    vm.runInContext("setSourceTab('forum')", context);
    html = el('sourcesView').innerHTML;
    assert.equal((html.match(/<tr data-index=/g) || []).length, feeds.sources.filter(src => src.type === 'forum').length);
    assert.ok(html.includes(`<div class="text-[10px] text-slate-600 font-mono-custom break-all">${esc(forum.url)}</div>`),
        'the feed link is shown under a forum, as for news sites');
    assert.equal((html.match(/data-field="weight"/g) || []).length, feeds.sources.filter(src => src.type === 'forum').length);
    assert.equal(el('addName').placeholder, 'Name');
    assert.match(add('https://forum.example.org/forums/retro.5/index.rss'), /Give the source a name\./);
    assert.match(add('forum.example.org/index.rss', 'No Scheme'), /Paste the full link of the feed/);
    assert.match(add('https://forum.example.org/forums/retro.5/index.rss', 'Example Retro'), /^Added Example Retro\./);
    assert.equal(evalJson("feedConfig.sources.find(s => s.name === 'Example Retro').type"), 'forum');
    assert.match(add(forum.url, 'Twice'), /is already in the list/);

    assert.deepEqual(evalJson('validateConfig(feedConfig)'), []);
    vm.runInContext('discardChanges()', context);
    assert.equal(evalJson("feedConfig.sources.some(s => s.board === 'vp')"), false);
    el('typeSelect').value = 'all';
});

await check('the theme: four colours with one job each, readable on every ground', () => {
    const css = read('retro.css');
    const page = read('index.html');
    const guide = read('guide.html');
    const tokens = Object.fromEntries([...css.matchAll(/^\s*--([a-z-]+): (#[0-9A-Fa-f]{6});/gm)].map(m => [m[1], m[2]]));

    // Readable: every colour that carries text, on every ground text sits on (WCAG AA, 4.5 to 1).
    const luminance = (hex) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
        .map(c => c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
        .reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
    const contrast = (a, b) => {
        const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
        return (hi + 0.05) / (lo + 0.05);
    };
    for (const ground of ['bg', 'banner', 'inset', 'stripe']) {
        for (const ink of ['text', 'body', 'dim', 'mute', 'accent', 'accent-hi', 'red', 'green', 'money']) {
            assert.ok(contrast(tokens[ink], tokens[ground]) >= 4.5, `--${ink} on --${ground}: ${contrast(tokens[ink], tokens[ground]).toFixed(2)}`);
        }
    }
    // A row under the pointer is tinted with the accent; the small print and the red tag sit on it too.
    const rgb = (hex) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
    const hex = (parts) => '#' + parts.map(part => Math.round(part).toString(16).padStart(2, '0')).join('');
    const tints = [...css.matchAll(/tr:hover \{ background-color: rgba\((\d+), (\d+), (\d+), (\.\d+)\); \}/g)]
        .map(m => ({ colour: [m[1], m[2], m[3]].map(Number), alpha: Number(m[4]) }));
    assert.equal(tints.length, 2, 'a plain row and a striped table row');
    for (const tint of tints) {
        assert.deepEqual(tint.colour, rgb(tokens.accent), 'the tint is the accent');
        for (const ground of ['bg', 'stripe']) {
            const under = hex(rgb(tokens[ground]).map((part, i) => part + (tint.colour[i] - part) * tint.alpha));
            for (const ink of ['text', 'body', 'dim', 'mute', 'accent', 'red', 'green', 'money']) {
                assert.ok(contrast(tokens[ink], under) >= 4.5, `--${ink} on a hovered row (${under}): ${contrast(tokens[ink], under).toFixed(2)}`);
            }
        }
    }
    // The stripe has to be seen to be of any use, and must not swallow the fields that sit on it.
    assert.ok(contrast(tokens.stripe, tokens.bg) >= 1.08, `--stripe against --bg: ${contrast(tokens.stripe, tokens.bg).toFixed(3)}`);
    assert.ok(contrast(tokens.line, tokens.stripe) >= 1.15, 'a field on a striped row keeps its outline');
    assert.ok(contrast(tokens.money, tokens['money-bg']) >= 4.5, 'a price link at rest');
    assert.ok(contrast(tokens.bg, tokens.money) >= 4.5, 'a price link under the pointer: dark on yellow');
    assert.ok(contrast(tokens.bg, tokens.accent) >= 4.5, 'the filled button: dark on blue');
    assert.ok(contrast(tokens.bg, tokens['accent-hi']) >= 4.5);

    // Yellow has one job: nothing but a price link is yellow.
    const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(m => [m[1].trim(), m[2]]);
    const yellow = rules.filter(([, body]) => /var\(--money/.test(body)).map(([selector]) => selector);
    assert.ok(yellow.length >= 2, 'at rest and under the pointer');
    assert.ok(yellow.every(selector => selector.split(',').every(part => /\.price-link\b/.test(part))), yellow.join(' | '));
    assert.match(css, /body \.price-link:hover, body \.price-link:focus-visible \{\s*background: var\(--money\);\s*border-color: var\(--money\);\s*color: var\(--bg\);/);
    // ...by no other route either: every colour is named once, at the top, and the strip's
    // yellow is used by the strip alone; the pages have no yellow of their own.
    const afterTokens = css.slice(css.indexOf('}', css.indexOf(':root {')) + 1).replace(/\/\*[\s\S]*?\*\//g, '');
    assert.deepEqual(afterTokens.match(/#[0-9A-Fa-f]{3,8}\b/g), null, 'no colour written out below the list at the top');
    assert.deepEqual(rules.filter(([, body]) => /var\(--strip-/.test(body)).map(([selector]) => selector), ['body .brand-bar::before']);
    assert.doesNotMatch(page + guide, /\b(?:text|bg|border|accent)-(?:yellow|orange)-\d/);
    // The classes the pages colour things with all go through those names.
    for (const mapping of [
        'body .text-cyan-400, body .text-cyan-300 { color: var(--accent); }', 'body .text-emerald-400 { color: var(--green); }',
        'body .text-red-400 { color: var(--red); }', 'body .text-slate-300 { color: var(--body); }', 'body .text-slate-400 { color: var(--dim); }',
        'body .text-slate-500, body .text-slate-600 { color: var(--mute); }', 'body .text-amber-400, body .text-amber-400\\/80 { color: var(--dim); }',
        'body input::placeholder { color: var(--mute); }', 'body input[type="checkbox"] { accent-color: var(--accent); }',
        'body .from-blue-600 { background-color: var(--accent); color: var(--bg); }',
    ]) assert.ok(css.includes(mapping), mapping);
    assert.match(css, /body \.brand-btn-primary \{\s*background: var\(--accent\);\s*border-color: var\(--accent\);\s*color: var\(--bg\);/);
    const named = (part) => rules.filter(([selector]) => selector.includes(part)).map(([selector]) => selector);
    assert.deepEqual(named('.remaster-tag'), ['body .remaster-tag'], 'one rule, so nothing further down undoes it');
    assert.deepEqual(named('.stat-value'), ['body .stat-value', 'body .stat-value.is-news', 'body .stat-value.is-live', 'body .stat-value']);
    // Red marks remaster news (the tag, the number at the top, the open page's line) and a low mood.
    assert.match(css, /body \.remaster-tag \{ border-color: var\(--red-line\); color: var\(--red\); \}/);
    assert.match(css, /body \.stat-value\.is-news \{ color: var\(--red\); \}/);
    assert.match(css, /body \.score-fill\.score-low \{ background: var\(--red\); \}/);
    // Teal is live and well: the sync dot, the active feeds, a good mood.
    assert.match(css, /body \.brand-dot \{[^}]*background: var\(--green\)/);
    assert.match(css, /body \.stat-value\.is-live \{ color: var\(--green\); \}/);
    assert.match(css, /body \.score-fill\.score-high \{ background: var\(--green\); \}/);
    assert.match(page, /<div id="statRemasters" class="stat-value is-news">/);
    assert.match(page, /<div id="statFeedsCount" class="stat-value is-live">/);
    assert.match(page, /<div id="statAvgSentiment" class="stat-value">/);
    // The tag in the table, beside a game's rank and beside a game named today is the same tag.
    assert.equal((script.match(/<span class="remaster-tag /g) || []).length, 3);
    context.__items = [{ headline: 'Okami HD announced', source: 'Eurogamer', link: 'https://e.example/okami', matched_game: 'Okami',
        is_remaster_rumor: true, sentiment: 50, timestamp: '2026-10-07 08:00 UTC' }];
    vm.runInContext('allFeedData = __items; refreshDashboard();', context);
    assert.match(el('feedTableBody').children[0].innerHTML, /<span class="remaster-tag border [^"]*">Remaster<\/span>\s*Okami HD announced/);
    assert.match(el('topGamesList').innerHTML, /<span class="remaster-tag [^"]*">1 remaster<\/span>/);

    // All four meet in the strip across the top of both pages, and in the mark.
    assert.match(css, /body \.brand-bar::before \{\s*content: "";\s*display: block;\s*height: 4px;\s*background: linear-gradient\(90deg,\s*var\(--strip-red\) 0 25%, var\(--strip-yellow\) 25% 50%, var\(--strip-teal\) 50% 75%, var\(--strip-blue\) 75% 100%\);\s*\}/);
    assert.deepEqual(named('.brand-bar'), ['body .brand-bar', 'body .brand-bar::before']);
    for (const [name, html] of [['index.html', page], ['guide.html', guide]]) {
        assert.match(html, /<header class="brand-bar">/, name);
        const mark = html.slice(html.indexOf('<header class="brand-bar">')).match(/<svg[\s\S]*?<\/svg>/)[0];
        assert.deepEqual([...mark.matchAll(/stroke="(#[0-9A-F]{6})"/g)].map(m => m[1]),
            [tokens['strip-red'], tokens['strip-yellow'], tokens['strip-blue'], tokens['strip-teal']], name);
        assert.match(html, new RegExp(`<meta name="theme-color" content="${tokens.banner}">`), name);
    }

    // The banner is the mark, the name and one line; what the site does is on the guide page.
    assert.match(page, /<h1 class="brand-word">Spindle<\/h1>\s*<p class="brand-tag">PS2 news, mentions and prices<\/p>/);
    assert.doesNotMatch(page + css, /blurb/);
    const lockup = page.slice(page.indexOf('<div class="brand-lock">'), page.indexOf('</header>'));
    assert.equal((lockup.match(/<p\b/g) || []).length, 1, 'one line under the name and no paragraph beside it');
    assert.match(css, /grid-template-areas: "id" "actions" "sync";/, 'on a phone: the name, the three buttons, the sync line');
    assert.match(guide, /Every game it recognises gets links out to shops and price guides, and eBay's asking prices beside its name\./);
    assert.doesNotMatch(guide, /amber/i, 'the guide calls the price buttons by the colour they are');
    assert.equal((guide.match(/yellow buttons/g) || []).length, 3);

    // Nothing of the palette before this one is left behind.
    for (const old of ['#080B12', '#0C1120', '#10141F', '#1E2636', '#141A28', '#101A2E', '#E8ECF5', '#C7D0E2', '#7E899F', '#4D5872',
        '#4C8DFF', '#7FADFF', '#F0A742', '#1B1508', '#6A4F1C', '#5FD3A8', '#E8646F', '#8E99AF', '76, 141, 255',
        '#0B0F1A', '#121826', '#232C42']) {
        assert.ok(!(css + page + guide).toUpperCase().includes(old.toUpperCase()), old);
    }
    vm.runInContext('allFeedData = []; refreshDashboard();', context);
});

await check('games first: what was named in the last day leads, and the table opens on the items that name a game', () => {
    const page = read('index.html');
    const now = Date.parse('2026-10-07T18:00:00Z');
    const stamp = (ms) => new Date(ms).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
    let link = 0;
    const row = (source, hoursAgo, games, extra = {}, base = now) => ({
        headline: `${source} item ${++link}`, source, link: `https://example.com/${link}`, matched_game: games.find(game => typeof game === 'string') ?? null,
        matched_games: games, matched_in: games.length ? 'title' : null, is_remaster_rumor: false, sentiment: 50, timestamp: stamp(base - hoursAgo * 3600e3), ...extra });
    context.__items = [
        row('Eurogamer', 1, ['Okami'], { is_remaster_rumor: true }),
        row('r/ps2', 2, ['Okami', 'Ico', 'Okami', 5, '  ']),               // one item, two games; a list with a repeat and junk in it
        row('YouTube: Some Channel', 3, ['Okami']),
        row('Destructoid', 4, ['Okami']),
        row('r/ps2', 5, ['Ico']),
        row('Eurogamer', 5.5, ['Okami']),                                   // the same source again: named once
        row('4chan /vr/', 6, ['Kuon'], { sentiment: null, source_type: '4chan' }),
        row('Forum: Lemmy games', 7, ['Retro'], { matched_in: 'body' }),    // found in the text only, twice:
        row('r/retrogaming', 8, ['Retro'], { matched_in: 'body' }),         // still below every game a headline named
        row('Push Square', 8.5, ['Mixed Game']),                            // one headline and two texts: three mentions,
        row('Push Square', 8.6, ['Mixed Game'], { matched_in: 'body' }),    // but below Ico's two headlines
        row('Kotaku', 8.7, ['Mixed Game'], { matched_in: 'body' }),
        row('Polygon', 9, []), row('Kotaku', 10, []), row('VG247', 23.9, []),
        row('Gematsu', 20, ['Zeta Game', 'Alpha Game']),                    // level on every count and on time: by name
        row('Eurogamer', 24.1, ['God Hand']),                               // a day and six minutes old: not "the last 24 hours"
        row('Gematsu', 100, ['Rule of Rose']),
        row('Kotaku', -0.5, ['Haunting Ground']),                           // a feed whose clock runs half an hour ahead
        row('Kotaku', -3, ['Silent Hill 2']),                               // three hours ahead is a wrong date, not news
        { headline: 'An older item with one game and no list', source: 'Push Square', link: 'https://example.com/old', matched_game: 'Black',
            is_remaster_rumor: false, sentiment: 50, timestamp: stamp(now - 12 * 3600e3) },
        { headline: 'No date at all', source: 'Push Square', link: 'https://example.com/undated', matched_game: 'Cars', matched_games: ['Cars'] },
        row('<b>Evil & Co</b>', 13, ['Ratchet & Clank <3']),                // names and sources are somebody else's text
        row('r/retrogaming', 30, [], { headline: 'Retro handhelds worth buying' }),
    ];
    vm.runInContext('feedConfig = JSON.parse(__text); rebuildSourceIndex(); allFeedData = __items; visibleFeedData = __items; gameFilter = null;', context);
    const recent = evalJson(`recentGames(__items, ${now})`);
    assert.deepEqual([recent.items, recent.naming], [19, 16], 'nineteen items in the window, sixteen of them naming a game');
    assert.deepEqual(recent.games.map(game => [game.name, game.headline, game.text]),
        [['Okami', 5, 0], ['Ico', 2, 0], ['Mixed Game', 1, 2], ['Haunting Ground', 1, 0], ['Kuon', 1, 0], ['Black', 1, 0],
            ['Ratchet & Clank <3', 1, 0], ['Alpha Game', 1, 0], ['Zeta Game', 1, 0], ['Retro', 0, 2]],
        'by headlines, then by all mentions, then the most recent, then by name; text-only last whatever its count');
    assert.deepEqual(recent.games[0].sources, ['Eurogamer', 'r/ps2', 'YouTube: Some Channel', 'Destructoid']);
    assert.equal(recent.games[0].remasters, 1);

    vm.runInContext(`renderRecentGames(__items, ${now})`, context);
    assert.equal(el('todaySummary').textContent,
        '16 items out of 19 published in the last 24 hours named a PS2 game: 10 games. The other 3 items are in the table further down, under Everything.');
    const rows = el('todayList').innerHTML.split('<li ').slice(1);
    assert.equal(rows.length, 10);
    assert.match(rows[0], /onclick="showGameRows\(0\)"[^>]*class="recent-game text-cyan-300 font-bold">Okami<\/button> <span class="remaster-tag [^"]*">1 remaster<\/span>/);
    assert.match(rows[0], />5 mentions<\/span>/);
    assert.match(rows[1], /class="recent-game text-cyan-300">Ico<\/button>/, 'only the first name is bold');
    assert.match(rows[0], /Eurogamer · r\/ps2 · YouTube: Some Channel <span class="text-slate-500">\+1 more<\/span>/, 'three sources named, the rest counted');
    assert.match(rows[2], />Mixed Game<\/button><\/span>\s*<span[^>]*>3 mentions<\/span>/, 'the count is of every mention, headline or text');
    assert.match(rows[4], />Kuon<\/button><\/span>\s*<span[^>]*>1 mention<\/span>/);
    assert.match(rows[4], /4chan \/vr\//);
    assert.match(rows[9], />Retro<\/button> <span class="[^"]*" title="Named in the text under a headline, not in the headline itself\. These are wrong more often\.">in the text only<\/span>/);
    assert.match(rows[9], />2 mentions<\/span>/);
    assert.doesNotMatch(rows.slice(0, 9).join(''), /in the text only/);
    assert.ok(rows.every(html => /class="price-links"/.test(html)), 'every game carries its price links');
    assert.match(rows[6], /onclick="showGameRows\(6\)"[^>]*>Ratchet &amp; Clank &lt;3<\/button>/);
    assert.match(rows[6], /&lt;b&gt;Evil &amp; Co&lt;\/b&gt;/);
    assert.doesNotMatch(el('todayList').innerHTML, /<b>Evil|Clank <3/, 'nothing from a feed reaches the page as markup');
    assert.deepEqual([...el('todayList').innerHTML.matchAll(/onclick="showGameRows\((\d+)\)"/g)].map(m => Number(m[1])), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
    assert.doesNotMatch(el('todayList').innerHTML, /God Hand|Rule of Rose|Silent Hill 2|Cars|Polygon|VG247/, 'nothing older, nothing undated, nothing without a game');
    assert.equal(el('todayListToggle').classList.contains('hidden'), true, 'ten games fit without a button');
    assert.deepEqual(evalJson('[LIST_FOLD.todayList, RECENT_HOURS]'), [10, 24]);
    assert.match(rows[4], /<div class="mt-1 text-\[11px\] text-slate-400">4chan \/vr\/<\/div>/, 'one source: its name and nothing after it');
    // The stylesheet says this about the new parts and nothing more: the first name keeps its
    // bold (no "font: inherit"), nothing is hidden, a name in the list keeps the height every
    // button has on a phone and the button in the sentence over the table stays near the text.
    const css = read('retro.css').replace(/\/\*[\s\S]*?\*\//g, '');
    const about = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(rule => [rule[1], rule[2]].map(part => part.replace(/\s+/g, ' ').trim()))
        .filter(([selector]) => /recent-game|#today|#feedSummary/.test(selector));
    assert.deepEqual(about, [
        ['body .recent-game', 'background: transparent; border: 0; padding: 0; text-align: left; cursor: pointer;'],
        ['body .recent-game:hover, body .recent-game:focus-visible', 'text-decoration: underline; text-underline-offset: 3px;'],
        ['body #feedSummary .recent-game', 'min-height: 2.1rem; vertical-align: middle;'],
        ['body #todayList > li > div:first-child, body #demandList > li > div:first-child, body #topGamesList > li > div:first-child, body #pricesList > li > div:first-child',
            'flex-wrap: wrap; row-gap: .25rem; font-size: .8125rem;'],
    ]);
    assert.match(css, /body main button, body main a\.bg-slate-800, body main \.from-blue-600 \{\s*min-height: 2\.75rem;/);
    // Everything the stylesheet hides. A rule added here on purpose belongs in this list; one
    // that hides the new list or the line over the table by where it sits does not.
    assert.deepEqual([...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(rule => /display:\s*none|visibility:\s*hidden/.test(rule[2])).map(rule => rule[1].replace(/\s+/g, ' ').trim()), [
        'body .is-folded > .list-extra', 'body .view-tab i, body .view-tab-count:not(.hidden)', 'body .price-links::-webkit-scrollbar', 'body #feedSection thead',
        'body #feedTableBody td[data-col="game"][data-unmatched]', 'body #sourceTabs::-webkit-scrollbar', 'body .sources-table > thead', 'body .sources-table td[data-col="remove"]:empty',
    ]);

    // The list sits first on the Tracker, above the Demand Index and the table.
    const order = ['class="stat-strip"', 'id="todaySection"', 'id="demandSection"', 'id="feedSection"'].map(mark => page.indexOf(mark));
    assert.ok(order.every((at, i) => at > 0 && (i === 0 || at > order[i - 1])), order.join(' '));
    assert.match(page, /<div id="todaySection" class="bg-ps2card p-6">\s*<div class="flex items-start justify-between gap-4 mb-4">\s*<div>\s*<h2>Named in the last 24 hours<\/h2>\s*<p id="todaySummary" class="text-xs text-slate-400">Loading\.\.\.<\/p>/);
    assert.match(page, /<ol id="todayList" class="zebra"><\/ol>\s*<button type="button" id="todayListToggle" onclick="toggleList\('todayList'\)" aria-controls="todayList"/);

    // The edges of the window and of the order, each on a small feed of its own.
    const edge = (items) => { context.__edge = items; return evalJson(`recentGames(__edge, ${now})`).games; };
    assert.deepEqual(edge([row('Kotaku', -0.9, ['A']), row('Kotaku', -1.5, ['B']), row('Kotaku', 23.9, ['C']), row('Kotaku', 24, ['D'])]).map(game => game.name), ['A', 'C'],
        'an hour of grace for a clock that runs ahead and no more; a day and not a minute over');
    assert.deepEqual(edge([row('A', 5, ['Early']), row('B', 3, ['Late']), row('C', 4, ['Late']), row('D', 2, ['Early'])]).map(game => [game.name, game.latest]),
        [['Early', stamp(now - 2 * 3600e3)], ['Late', stamp(now - 3 * 3600e3)]], 'a game is as recent as its newest mention, whatever order the items came in');
    // Which games an item names is decided in one place, for the list, the table and its line.
    context.__odd = [{ ...row('Kotaku', 1, []), matched_games: ['Listed Only'] }, { ...row('Kotaku', 2, []), matched_game: 'Old Style', matched_games: [] },
        { ...row('Kotaku', 3, ['No Source']), source: undefined }, row('Kotaku', 4, [])];
    assert.deepEqual(evalJson('__odd.map(gamesOf)'), [['Listed Only'], ['Old Style'], ['No Source'], []]);
    assert.deepEqual(edge(context.__odd).map(game => [game.name, game.sources]), [['Listed Only', ['Kotaku']], ['Old Style', ['Kotaku']], ['No Source', []]]);
    context.__edge = [row('One', 1, ['Solo'], { is_remaster_rumor: true }), row('Two', 2, ['Solo'], { is_remaster_rumor: true }), row('Three', 3, ['Solo'])];
    vm.runInContext(`renderRecentGames(__edge, ${now})`, context);
    assert.match(el('todayList').innerHTML, />2 remaster<\/span>/);
    assert.match(el('todayList').innerHTML, /<div class="mt-1 text-\[11px\] text-slate-400">One · Two · Three<\/div>/, 'three sources: all named and nothing "more"');
    vm.runInContext('renderTopGames(__edge)', context);
    assert.match(el('topGamesList').innerHTML, />2 remaster<\/span>/);

    // A quiet day, and a feed that has not moved, each say so instead of showing an empty box.
    vm.runInContext(`renderRecentGames(__items.filter(item => !item.matched_game), ${now})`, context);
    assert.equal(el('todaySummary').textContent, 'None of the 3 items published in the last 24 hours names a PS2 game.');
    assert.match(el('todayList').innerHTML, /No games to show yet\./);
    assert.deepEqual(evalJson('recentGameNames'), [], 'and no name is left to click');
    vm.runInContext(`renderRecentGames(__items, ${now + 30 * 86400e3})`, context);
    assert.match(el('todaySummary').textContent, /^Nothing published in the last 24 hours has come in\./);
    // Twelve games: ten show, a button opens the other two.
    context.__many = Array.from({ length: 12 }, (_, i) => row('Eurogamer', 1 + i, [`Game ${i}`]));
    vm.runInContext(`renderRecentGames(__many, ${now})`, context);
    assert.equal((el('todayList').innerHTML.match(/list-extra/g) || []).length, 2);
    assert.match(el('todayListToggle').innerHTML, /^Show 2 more/);
    assert.equal(el('todayListToggle').classList.contains('hidden'), false);
    assert.equal(el('todaySummary').textContent, '12 items out of 12 published in the last 24 hours named a PS2 game: 12 games.', 'no "other 0 items"');
    // A big day: nothing is left out however long the feed or the list, the numbers are written
    // for reading, and a name past the fold works like any other.
    const pad = (n) => String(n).padStart(2, '0');
    context.__big = Array.from({ length: 1200 }, (_, i) => row('Eurogamer', 1 + (i % 20), [`Game ${pad(i % 30)}`]));
    const big = evalJson(`recentGames(__big, ${now})`);
    assert.deepEqual([big.items, big.naming, big.games.length, [...new Set(big.games.map(game => game.headline))]], [1200, 1200, 30, [40]]);
    vm.runInContext(`visibleFeedData = __big; renderRecentGames(__big, ${now})`, context);
    assert.equal(el('todaySummary').textContent, '1,200 items out of 1,200 published in the last 24 hours named a PS2 game: 30 games.');
    assert.equal(el('todayList').innerHTML.split('<li ').length - 1, 30);
    assert.equal((el('todayList').innerHTML.match(/list-extra/g) || []).length, 20);
    assert.equal(el('todayList').classList.contains('is-folded'), true);
    vm.runInContext("toggleList('todayList'); showGameRows(29)", context);
    assert.equal(evalJson('gameFilter'), evalJson('recentGameNames[29]'));
    assert.equal(el('todayList').classList.contains('is-folded'), false, 'a list that was opened stays open when a name in it is pressed');
    assert.equal(el('feedTableBody').children.length, 40);
    vm.runInContext("toggleList('todayList'); clearGameFilter()", context);
    assert.equal(el('feedSummary').textContent, '1,200 of 1,200 items name a PS2 game.');
    el('filterSelect').value = 'all';
    vm.runInContext('onFeedFilterChange()', context);
    assert.equal(el('feedSummary').textContent, 'Everything: 1,200 items, 1,200 of them naming a PS2 game.');
    // One game with more items than a page holds: the next page is still that game's.
    context.__long = [...Array.from({ length: 130 }, (_, i) => row('Eurogamer', 1 + (i % 20), ['Big Game'])), row('Kotaku', 1, ['Small Game'])];
    vm.runInContext(`visibleFeedData = __long; renderRecentGames(__long, ${now}); showGameRows(0); goToPage(2)`, context);
    assert.deepEqual([evalJson('gameFilter'), el('feedTableBody').children.length], ['Big Game', 30]);
    assert.match(el('feedSummary').innerHTML, /^The 130 items in the feed that name Big Game\. <button/);
    assert.match(el('pagination').innerHTML, /Showing 101–130 of 130/);
    vm.runInContext(`clearGameFilter(); renderRecentGames(__big, ${now})`, context);
    assert.equal(el('todayListToggle').classList.contains('hidden'), false);
    vm.runInContext(`renderRecentGames([], ${now})`, context);
    assert.equal(el('todayListToggle').classList.contains('hidden'), true, 'an empty list has no button left under it');
    el('filterSelect').value = 'matched';

    // The table opens on the items that name a game, and its line says what is shown: with the
    // box and the menus applied, so it never describes rows that are not there.
    assert.match(page, /<option value="matched" selected>PS2 Games Only<\/option>\s*<option value="remaster">Remaster News Only<\/option>\s*<option value="all">Everything<\/option>/);
    // The line has a row to itself between the menus and the table, so its length moves nothing;
    // a change is announced, and it can take the keyboard's place when a button in it goes.
    assert.match(page, /<\/select>\s*<\/div>\s*<\/div>\s*<p id="feedSummary" tabindex="-1" aria-live="polite" class="text-xs text-slate-400 mb-4">[^<]*<\/p>\s*<div class="overflow-x-auto">\s*<table/);
    const tableRows = () => el('feedTableBody').children.filter(child => /data-col="source"/.test(child.innerHTML));
    const shown = (filter, search = '', type = 'all') => {
        el('filterSelect').value = filter; el('searchInput').value = search; el('typeSelect').value = type;
        vm.runInContext('onFeedFilterChange()', context);
        return [tableRows().length, el('feedSummary').textContent];
    };
    vm.runInContext(`visibleFeedData = __items; renderRecentGames(__items, ${now})`, context);
    assert.deepEqual(shown('matched'), [20, '20 of 24 items name a PS2 game. Choose Everything for the other 4.']);
    assert.deepEqual(shown('all'), [24, 'Everything: 24 items, 20 of them naming a PS2 game.']);
    assert.deepEqual(shown('remaster'), [1, '1 of 24 items is flagged as remaster news.']);
    assert.deepEqual(shown('all', 'ico'), [2, 'Listing 2 of the 24 items in the feed.'], 'a search looks at every game an item names, not only the first');
    assert.deepEqual(shown('matched', 'polygon'), [0, 'Listing 0 of the 20 items that name a PS2 game.']);
    assert.deepEqual(shown('matched', '', 'reddit'), [3, 'Listing 3 of the 20 items that name a PS2 game.']);
    assert.deepEqual(shown('matched', '', '4chan'), [1, 'Listing 1 of the 20 items that name a PS2 game.']);
    assert.deepEqual(shown('remaster', 'nothing like this'), [0, 'Listing 0 of the 1 item flagged as remaster news.']);
    assert.match(page, /<select id="filterSelect" onchange="onFeedFilterChange\(\)" aria-label="Which items to show"/);
    vm.runInContext('visibleFeedData = __odd', context);
    assert.deepEqual(shown('matched'), [3, '3 of 4 items name a PS2 game. Choose Everything for the other 1.']);
    assert.deepEqual(shown('all', 'old style'), [1, 'Listing 1 of the 4 items in the feed.']);
    // One of anything is written as one.
    vm.runInContext('visibleFeedData = __items.slice(0, 1)', context);
    assert.deepEqual([shown('matched')[1], shown('remaster')[1], shown('all')[1], shown('matched', 'x')[1]],
        ['1 of 1 item names a PS2 game.', '1 of 1 item is flagged as remaster news.', 'Everything: 1 item, 1 of them naming a PS2 game.', 'Listing 0 of the 1 item that names a PS2 game.']);
    vm.runInContext('visibleFeedData = __items', context);
    assert.doesNotMatch(vm.runInContext('filterFeedItems.toString()', context), /`Showing|'Showing/, 'the line under the table says "Showing 1–100 of 412": this one starts another way');
    for (const control of ['searchInput" oninput', 'filterSelect" onchange', 'typeSelect" onchange']) {
        assert.ok(page.includes(`id="${control}="onFeedFilterChange()"`), control);
    }

    // A row names every game its item names: the first leads, the rest follow.
    shown('all');
    const cell = (headline) => tableRows().map(child => child.innerHTML).find(html => html.includes(headline)).match(/<td data-col="game"[\s\S]*?<\/td>/)[0];
    assert.match(cell('r/ps2 item 2'), /text-cyan-300">Okami<span class="price-links"[\s\S]*<div class="[^"]*">also names Ico<\/div>/);
    assert.match(cell('Gematsu item 16'), />Zeta Game<[\s\S]*also names Alpha Game</);
    assert.doesNotMatch(cell('Eurogamer item 1'), /also names/);
    assert.match(cell('Polygon item 13'), /data-unmatched[^>]*><span class="text-slate-500">Unmatched \/ General<\/span>/);
    context.__crowd = [row('r/ps2', 1, ['A<1>', 'B<2>', 'C3', 'D4', 'E5', 'F6', 'The G7 Saga', 'G7 Two'])];
    vm.runInContext('visibleFeedData = __crowd; filterFeedItems();', context);
    assert.match(tableRows()[0].innerHTML, /text-cyan-300">A&lt;1&gt;<[\s\S]*also names B&lt;2&gt;, C3, D4, E5 and 3 more<\/div>/);
    assert.doesNotMatch(tableRows()[0].innerHTML, /A<1>|B<2>/);
    // A search that found games far down an item's list shows them, in their order, not "and 3
    // more": typed in capitals, found in the middle of a name, with the space a phone leaves.
    for (const typed of ['G7', ' g7 ']) {
        assert.equal(shown('all', typed)[0], 1, typed);
        assert.match(tableRows()[0].innerHTML, /also names The G7 Saga, G7 Two, B&lt;2&gt;, C3 and 3 more<\/div>/, typed);
    }
    vm.runInContext('renderTopGames(__crowd)', context);
    assert.equal(el('topGamesSummary').textContent, 'Share of all PS2 game mentions: 8 mentions across 8 games.', 'Most Mentioned Games counts every one of them');
    context.__crowd = [row('r/ps2', 1, ['A', 'B', 'C', 'D', 'E'])];
    vm.runInContext('visibleFeedData = __crowd;', context);
    shown('all');
    assert.match(tableRows()[0].innerHTML, /also names B, C, D, E<\/div>/, 'four others: all named and nothing "more"');
    vm.runInContext('visibleFeedData = __items; filterFeedItems();', context);

    // A game's name in the list opens the table on exactly the items that name it, from the
    // whole feed, whatever the box and the menus said; and the table says so.
    let scrolled = 0, focused = 0;
    el('feedSection').scrollIntoView = () => { scrolled++; };
    el('feedSummary').focus = (how) => { focused += how.preventScroll ? 1 : 100; };
    el('filterSelect').value = 'remaster'; el('typeSelect').value = 'podcast'; el('searchInput').value = 'something else';
    vm.runInContext('showGameRows(1)', context);
    assert.deepEqual([el('searchInput').value, el('filterSelect').value, el('typeSelect').value, scrolled, focused], ['', 'matched', 'all', 1, 1]);
    assert.deepEqual(tableRows().map(child => child.innerHTML.match(/r\/ps2 item \d+/)[0]), ['r/ps2 item 2', 'r/ps2 item 5']);
    assert.match(cell('r/ps2 item 2'), /text-cyan-300">Ico<[\s\S]*also names Okami</, 'the game asked for leads its rows');
    assert.match(cell('r/ps2 item 2'), /aria-label="Price lookups for Ico"/);
    assert.doesNotMatch(cell('r/ps2 item 2'), /Price lookups for Okami/, 'with its own prices, not the first game\'s');
    assert.equal(el('feedSummary').innerHTML,
        'The 2 items in the feed that name Ico. <button type="button" onclick="clearGameFilter()" class="recent-game text-cyan-400 underline">Back to every game</button>');
    vm.runInContext('showGameRows(1)', context);
    assert.deepEqual([scrolled, focused], [2, 2], 'pressed again from further up the page, it goes to the table again');
    vm.runInContext('showGameRows(9)', context);   // Retro: not the subreddit with "retro" in its name, not the headline about handhelds
    assert.deepEqual(tableRows().map(child => child.innerHTML.match(/(?:Forum: Lemmy games|r\/retrogaming) item \d+/)[0]), ['Forum: Lemmy games item 8', 'r/retrogaming item 9']);
    vm.runInContext('showGameRows(6)', context);
    assert.match(el('feedSummary').innerHTML, /^The 1 item in the feed that names Ratchet &amp; Clank &lt;3\. <button/);
    vm.runInContext('showGameRows(99)', context);
    assert.equal(evalJson('gameFilter'), 'Ratchet & Clank <3', 'a name that is not there changes nothing');
    vm.runInContext("gameFilter = 'Gone <b>'; filterFeedItems()", context);
    assert.match(el('feedSummary').innerHTML, /^No item in the feed names Gone &lt;b&gt; now\. <button/);
    vm.runInContext('showGameRows(6)', context);
    // It ends with the button, which hands the keyboard to the line it was in, or with any
    // change made by hand.
    focused = 0;
    vm.runInContext('clearGameFilter()', context);
    assert.deepEqual([evalJson('gameFilter'), tableRows().length, el('feedSummary').textContent, focused],
        [null, 20, '20 of 24 items name a PS2 game. Choose Everything for the other 4.', 1]);
    vm.runInContext('showGameRows(0)', context);
    assert.equal(tableRows().length, 5);
    assert.deepEqual(shown('all', 'kuon'), [1, 'Listing 1 of the 24 items in the feed.']);
    assert.deepEqual([evalJson('gameFilter'), focused], [null, 2], 'typing in the box keeps the keyboard in the box');

    // Most Mentioned Games counts the same way: an item that names two games is a mention of each.
    vm.runInContext('renderTopGames(__items)', context);
    assert.equal(el('topGamesSummary').textContent, 'Share of all PS2 game mentions: 22 mentions across 14 games.');
    assert.equal(el('tabMentionsCount').textContent, '14');
    const ranked = el('topGamesList').innerHTML.split('<li ').slice(1);
    assert.match(ranked[0], /#1 Okami[\s\S]*>5 mentions · 23%</);
    assert.match(ranked.find(html => / Ico</.test(html)), />2 mentions · 9\.1%</, 'named second in one item, first in another');
    assert.ok(ranked.some(html => / Alpha Game</.test(html)), 'a game only ever named second is ranked too');

    // The page draws all of it by itself, from the sources that are switched on.
    const feeds = context.__feeds;
    const [first, second] = feeds.sources.filter(src => src.enabled && src.type === 'news');
    const live = (src, game, hoursAgo) => row(src.name, hoursAgo, [game], { source_type: 'news', feed: src.url }, Date.now());
    context.__live = [{ ...live(first, 'Okami', 1), is_remaster_rumor: true }, live(second, 'Ico', 3), live(first, 'Ico', 4), row('Polygon', 2, [], {}, Date.now())];
    el('todaySummary').textContent = ''; el('todayList').innerHTML = ''; el('feedSummary').textContent = '';
    el('searchInput').value = ''; el('filterSelect').value = 'matched'; el('typeSelect').value = 'all';
    vm.runInContext('feedConfig = JSON.parse(__text); allFeedData = __live; onConfigChanged();', context);
    assert.equal(el('todaySummary').textContent,
        '3 items out of 4 published in the last 24 hours named a PS2 game: 2 games. The other 1 item is in the table further down, under Everything.');
    assert.match(el('todayList').innerHTML, />Ico<\/button>[\s\S]*>2 mentions<[\s\S]*>Okami<\/button>/);
    assert.equal(el('feedSummary').textContent, '3 of 4 items name a PS2 game. Choose Everything for the other 1.');
    assert.equal(shown('remaster')[1], '1 of 4 items is flagged as remaster news.');
    // A game is chosen, and then the only source that named it is switched off: the table says so.
    vm.runInContext('showGameRows(1)', context);
    assert.equal(evalJson('gameFilter'), 'Okami');
    vm.runInContext(`feedConfig.sources.find(src => src.url === ${JSON.stringify(first.url)}).enabled = false; onConfigChanged();`, context);
    assert.equal(el('todaySummary').textContent,
        '1 item out of 2 published in the last 24 hours named a PS2 game: 1 game. The other 1 item is in the table further down, under Everything.');
    assert.doesNotMatch(el('todayList').innerHTML, /Okami/, 'a switched-off source leaves the list at once');
    assert.equal(el('feedSummary').innerHTML,
        'No item in the feed names Okami now. <button type="button" onclick="clearGameFilter()" class="recent-game text-cyan-400 underline">Back to every game</button>');
    assert.equal(tableRows().length, 0);
    vm.runInContext('clearGameFilter()', context);
    assert.equal(el('feedSummary').textContent, '1 of 2 items names a PS2 game. Choose Everything for the other 1.');
    assert.equal(shown('remaster')[1], '0 of 2 items are flagged as remaster news.', 'what a switched-off source flagged is not counted');
    shown('matched');
    vm.runInContext('showGameRows(0)', context);
    assert.match(el('feedSummary').innerHTML, /^The 1 item in the feed that names Ico\. <button/, 'and its items are not brought back by a click on the game');
    assert.equal(tableRows().length, 1);
    // The choice lasts through a reload of the data, and follows the sources as they change.
    vm.runInContext('refreshDashboard()', context);
    assert.deepEqual([evalJson('gameFilter'), tableRows().length], ['Ico', 1]);
    vm.runInContext(`feedConfig.sources.find(src => src.url === ${JSON.stringify(first.url)}).enabled = true; onConfigChanged();`, context);
    assert.deepEqual([evalJson('gameFilter'), tableRows().length], ['Ico', 2]);
    assert.match(el('feedSummary').innerHTML, /^The 2 items in the feed that name Ico\. <button/);
    vm.runInContext('clearGameFilter()', context);
    // A long feed through the page itself: nothing is cut short on the way to the list, a thread
    // from 4chan is in it, and a list that was opened stays open through a click and a reload,
    // which leaves the keyboard where it was.
    context.__bigLive = [...Array.from({ length: 1200 }, (_, i) => row('Eurogamer', 1 + (i % 20), [`Game ${pad(i % 30)}`], {}, Date.now())),
        row('4chan /vr/', 2, ['Kuon'], { sentiment: null, source_type: '4chan' }, Date.now())];
    focused = 0;
    vm.runInContext("allFeedData = __bigLive; onConfigChanged(); toggleList('todayList'); showGameRows(30);", context);
    assert.equal(el('todaySummary').textContent, '1,201 items out of 1,201 published in the last 24 hours named a PS2 game: 31 games.');
    assert.equal(evalJson('gameFilter'), 'Kuon');
    vm.runInContext('refreshDashboard()', context);
    assert.equal(el('todayList').classList.contains('is-folded'), false);
    assert.deepEqual([evalJson('gameFilter'), tableRows().length, focused], ['Kuon', 1, 1]);
    vm.runInContext("toggleList('todayList'); clearGameFilter()", context);
    // Before the first scrape the stand-in items are shown, and nothing claims the robot is late.
    vm.runInContext('feedConfig = JSON.parse(__text); allFeedData = fallbackData.items; onConfigChanged();', context);
    assert.equal(el('todaySummary').textContent, 'No feed has been loaded, so there is nothing to list yet.');
    assert.equal(el('feedSummary').textContent, '2 of 2 items name a PS2 game.', 'no "other 0"');

    el('searchInput').value = ''; el('filterSelect').value = 'all';
    vm.runInContext('gameFilter = null; allFeedData = []; refreshDashboard();', context);
});

await check('prices: the last day\'s games are ordered by price, and a median says how it moved in a week', () => {
    const now = Date.parse('2026-10-14T12:00:00Z');
    const stamp = (hoursAgo) => new Date(now - hoursAgo * 3600e3).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
    const item = (game, hoursAgo, where = 'title') => ({ headline: `${game} news`, source: `Source ${hoursAgo}`, link: `https://e.example/${game}/${hoursAgo}`,
        matched_game: game, matched_games: [game], matched_in: where, is_remaster_rumor: false, sentiment: 50, timestamp: stamp(hoursAgo) });
    const site = (median, week, extra = {}) => ({ checked: '2026-10-14T10:00Z', copies: 9, lowest: median / 2, median, postage: 3,
        ...(week === undefined ? {} : { week }), ...extra });
    const wk = (median) => ({ checked: '2026-10-07T09:00Z', median });
    const prices = { currencies: { US: 'USD', UK: 'GBP' }, games: {
        'Cheap UK': { level: 'normal', mentions: 3, UK: site(5, wk(4)), US: site(500) },     // pounds decide, whatever the dollars say
        'Dear UK': { level: 'normal', mentions: 3, UK: site(80, wk(80)) },
        'Also Dear UK': { level: 'normal', mentions: 3, UK: site(80) },
        'Dollars Only': { level: 'normal', mentions: 3, US: site(200, wk(250)), UK: { checked: '2026-10-14T10:00Z', unmatched: true } },
        'Few Dollars': { level: 'normal', mentions: 3, US: site(10), UK: { checked: '2026-10-14T10:00Z', copies: 0, lowest: null, median: null, postage: null } },
        'Shin Megami Tensei: Persona 4': { level: 'normal', mentions: 3, UK: site(73.49, wk(71.19)) },
    } };
    context.__p = prices;
    vm.runInContext('setPrices(__p, { games: [{ title: "Shin Megami Tensei: Persona 4", search: "Persona 4" }] })', context);
    // In the order recentGames() would give: by headlines, then mentions.
    context.__items = [
        item('Unpriced Hit', 1), item('Unpriced Hit', 2), item('Unpriced Hit', 3),
        item('Cheap UK', 1), item('Cheap UK', 2), item('Few Dollars', 1), item('Few Dollars', 2),
        item('Dear UK', 4), item('Dollars Only', 5), item('Also Dear UK', 6), item('Persona 4', 7),
        item('Retro', 1, 'body'),
    ];
    vm.runInContext(`allFeedData = __items; visibleFeedData = __items; renderRecentGames(__items, ${now})`, context);
    const names = evalJson('recentGameNames');
    assert.deepEqual(names, ['Dear UK', 'Also Dear UK', 'Persona 4', 'Cheap UK', 'Dollars Only', 'Few Dollars', 'Unpriced Hit', 'Retro'],
        'pounds first, dearest at the top (a tie keeps the usual order), then dollars where there are no pounds, then no price');
    const rows = el('todayList').innerHTML.split('<li ').slice(1);
    assert.deepEqual(rows.map(html => html.match(/onclick="showGameRows\((\d+)\)"[^>]*>([^<]*)</).slice(1)), names.map((name, i) => [String(i), name]));
    assert.match(rows[0], /class="recent-game text-cyan-300 font-bold">Dear UK</, 'the dearest is the one in bold');
    assert.match(el('todaySummary').textContent, /: 8 games\. Most expensive first, by the eBay UK median \(US where there is no UK figure\); games without a price last\.$/);
    assert.equal(el('todayListToggle').classList.contains('hidden'), true);
    vm.runInContext('showGameRows(0)', context);
    assert.equal(evalJson('gameFilter'), 'Dear UK', 'a name opens the game it shows');
    vm.runInContext('clearGameFilter()', context);

    // The change beside each median, in the list and wherever else a median is shown.
    assert.match(rows[2], /<span class="ebay-flag">UK<\/span><b>£73\.49<\/b><span class="ebay-change is-up" title="A week before \((?:7 Oct|Oct 7)\) the median was £71\.19: up £2\.30, 3\.2%\.">\(£2\.30 ▲ 3\.2%\)<\/span><\/a>/);
    assert.match(rows[2], /title="Median asking price of 9 used copies on eBay UK, cheapest £36\.75, checked [^"]*; a week before it was £71\.19\. Opens/);
    assert.match(rows[0], /<b>£80\.00<\/b><span class="ebay-change" title="A week before \((?:7 Oct|Oct 7)\) the median was £80\.00: the same\.">\(no change\)<\/span>/);
    assert.match(rows[1], /<b>£80\.00<\/b><\/a>/, 'no figure from a week before: nothing in brackets');
    assert.match(rows[3], /<b>£5\.00<\/b><span class="ebay-change is-up"[^>]*>\(£1\.00 ▲ 25%\)<\/span>/);
    assert.match(rows[4], /<b>\$200<\/b><span class="ebay-change is-down" title="A week before \((?:7 Oct|Oct 7)\) the median was \$250: down \$50\.00, 20%\.">\(\$50\.00 ▼ 20%\)<\/span>/);

    const change = (median, week, currency = 'GBP') => {
        context.__site = { checked: '2026-10-14T10:00Z', copies: 3, median, week };
        return vm.runInContext(`priceChangeHtml(__site, ${JSON.stringify(currency)}, 'en-GB')`, context);
    };
    // Worked out from the prices as shown: whole pounds from £100, so the bracket adds up.
    assert.match(change(100.04, wk(100)), /title="A week before \((?:7 Oct|Oct 7)\) the median was £100: the same\.">\(no change\)</);
    assert.match(change(150.49, wk(99.99)), /is-up[^>]*>\(£50\.01 ▲ 50%\)</);
    assert.match(change(50.02, wk(50)), /is-up[^>]*>\(£0\.02 ▲ &lt;0\.1%\)</);
    assert.match(change(50.05, wk(50)), /is-up[^>]*>\(£0\.05 ▲ 0\.1%\)</);
    assert.match(change(3.3, wk(3)), /is-up[^>]*>\(£0\.30 ▲ 10%\)</, 'ten per cent, not "10.0"');
    assert.match(change(54.98, wk(50)), /is-up[^>]*>\(£4\.98 ▲ 10%\)</, '9.96 per cent is written as ten too');
    // The date in the hint is the reader's own, like every other time on the page.
    const late = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(new Date('2026-10-07T23:30:00Z'));
    context.__site = { checked: '2026-10-14T23:00Z', copies: 3, median: 12, week: { checked: '2026-10-07T23:30Z', median: 10 } };
    assert.ok(vm.runInContext("priceChangeHtml(__site, 'GBP', 'en-GB')", context).includes(`A week before (${late}) the median`), late);
    assert.match(change(0.01, wk(20)), /is-down[^>]*>\(£19\.99 ▼ &gt;99%\)</, 'a fall short of everything is not "100%"');
    assert.doesNotMatch(change(10, wk(10), '<b>'), /<b>/, 'the hint of an unchanged price is escaped too');
    assert.match(change(99.5, wk(100)), /is-down[^>]*>\(£0\.50 ▼ 0\.5%\)</);
    assert.match(change(30, wk(10)), /is-up[^>]*>\(£20\.00 ▲ 200%\)</);
    assert.match(change(10.1, wk(10)), />\(£0\.10 ▲ 1\.0%\)</, 'pennies are counted as pennies');
    for (const bad of [undefined, null, 'x', {}, { checked: '2026-10-07T09:00Z' }, { checked: 'last week', median: 10 },
        { checked: '2026-10-07T09:00Z', median: 0 }, { checked: '2026-10-07T09:00Z', median: '10' }, { checked: '2026-10-07T09:00Z', median: -1 }]) {
        assert.equal(change(12, bad), '', JSON.stringify(bad));
    }
    assert.equal(change(null, wk(10)), '', 'nothing now, nothing to compare');
    assert.match(change(12, wk(10), '<b>'), />\(2\.00 &lt;b&gt; ▲ 20%\)</);
    assert.doesNotMatch(change(12, wk(10), '<b>'), /<b>/, 'a currency the browser does not know is text, never markup');

    // The eBay prices page: the change sits beside the median, the rest of the line as before.
    const pageRows = showPrices(prices).split('<li ').slice(1);
    const persona = pageRows.find(html => html.includes('Persona 4'));
    assert.match(persona, /<span class="ebay-site"><span class="ebay-flag">UK<\/span><span class="ebay-now"><b class="ebay-median">£73\.49<\/b> <span class="ebay-change is-up"[^>]*>\(£2\.30 ▲ 3\.2%\)<\/span><\/span><span class="ebay-rest">median · from £36\.75/);
    const plain = pageRows.find(html => html.includes('Also Dear UK'));
    assert.match(plain, /<span class="ebay-flag">UK<\/span><b class="ebay-median">£80\.00<\/b><span class="ebay-rest">/);

    // Without prices the list keeps its usual order and says nothing about prices.
    vm.runInContext(`setPrices(null, null); renderRecentGames(__items, ${now})`, context);
    assert.deepEqual(evalJson('recentGameNames'), ['Unpriced Hit', 'Cheap UK', 'Few Dollars', 'Dear UK', 'Dollars Only', 'Also Dear UK', 'Persona 4', 'Retro']);
    assert.doesNotMatch(el('todaySummary').textContent, /expensive/);
    assert.doesNotMatch(el('todayList').innerHTML, /ebay-change/);

    const css = read('retro.css');
    assert.match(css, /body \.ebay-change \{ font-size: \.72rem; font-weight: 400; color: var\(--dim\); white-space: nowrap; \}\nbody \.ebay-change\.is-up \{ color: var\(--green\); \}\nbody \.ebay-change\.is-down \{ color: var\(--red\); \}\n\/\* An overdue figure is dimmed, and so is how it moved \*\/\nbody \.ebay-site\.is-stale \.ebay-change, body \.ebay-quote\.is-stale \.ebay-change \{ opacity: \.5; \}/);
    vm.runInContext('allFeedData = []; visibleFeedData = []; refreshDashboard();', context);
});

console.log(`dashboard checks passed (${passed})`);
