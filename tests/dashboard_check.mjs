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
        addEventListener() {}, scrollIntoView() {}, reset() {}, click() {}, remove() {},
        appendChild(child) { this.children.push(child); },
    };
    // Like the DOM: assigning innerHTML replaces the element's children.
    Object.defineProperty(element, 'innerHTML', { get: () => html, set: (value) => { html = value; element.children = []; } });
    return element;
}
const elements = new Map();
const defaults = { filterSelect: 'all', typeSelect: 'all', sourceShow: 'all' };
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
    assert.match(el('sourcesView').innerHTML, /data-poll="podcast"[^>]*value="6"/);
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

    // The three places a game's name appears on the Tracker.
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

    // No price file: every list looks as it did before prices existed.
    showPrices(null);
    vm.runInContext('renderTopGames(__games); renderTable(__games)', context);
    assert.doesNotMatch(el('topGamesList').innerHTML + el('feedTableBody').children.map(row => row.innerHTML).join(''), /ebay-quote/);
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
    assert.match(read('retro.css'), /body \.view-tab\.is-active \{[^}]*border-bottom-color: var\(--accent\)/);
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
        row({ headline: 'Thread on /vr/ naming Okami', source: '4chan /vr/', source_type: '4chan', feed: '4chan:vr', matched_game: 'Okami',
            link: 'https://boards.4chan.org/vr/thread/101' }),
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
    // A thread has no mood score at all, so no weight can bring its placeholder 50 into the
    // average: not a weight on the role, not one on the board, and not a board the list has lost.
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

console.log(`dashboard checks passed (${passed})`);
