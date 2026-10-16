// Offline checks for the dashboard's inline script in index.html (run by tests/test_scraper.py).
//   node tests/dashboard_check.mjs                  runs the checks below
//   node tests/dashboard_check.mjs --validate FILE  prints validateConfig() verdicts for the configs in FILE
//   node tests/dashboard_check.mjs --price-keys FILE  prints priceKey() for the titles in FILE
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
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
            add: (...names) => names.forEach(c => classes.add(c)), remove: (...names) => names.forEach(c => classes.delete(c)), contains: (c) => classes.has(c),
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

await check('switched-off sources hide their items', () => {
    vm.runInContext(`
        feedConfig = JSON.parse(__text);
        rebuildSourceIndex();
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

await check('dashboard renders every view', () => {
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
    assert.equal(el('statTotalItems').innerText, 4);
    assert.equal(el('statFeedsCount').innerText, feeds.sources.filter(s => s.enabled).length);
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
    assert.match(el('sourcesView').innerHTML, /Fetch schedule/);
    assert.doesNotMatch(el('sourcesView').innerHTML, /Role weights/);
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
    assert.match(el('sourcesView').innerHTML, /<select data-poll="forum"[^>]*>(?:(?!<\/select>)[\s\S])*<option value="1" selected>1 hour<\/option>/);
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
    for (const col of ['source', 'headline', 'game', 'action']) {
        assert.match(matched, new RegExp(`<td data-col="${col}"`), `feed cell ${col}`);
    }
    assert.doesNotMatch(matched, /data-unmatched/);
    assert.match(unmatched, /<td data-col="game" data-unmatched/, 'an unmatched row says so, so a phone can drop the empty cell');

    // Source rows: every cell is named, and each statistic carries its column heading as a label.
    vm.runInContext(`setSourceTab('youtube')`, context);
    const youtube = el('sourcesView').innerHTML;
    assert.match(youtube, /<table class="sources-table /);
    for (const col of ['on', 'source', 'role', 'stat', 'status', 'remove']) {
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
    // The Demand Index page: ten rows, at most 25.
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
    assert.deepEqual(await demand(14), { rows: 14, extra: 4, folded: true, buttonHidden: false, button: 'Show 4 more' });
    assert.equal(el('demandListToggle').getAttribute('aria-expanded'), 'false');
    vm.runInContext("toggleList('demandList')", context);
    assert.deepEqual(await demand(), { rows: 14, extra: 4, folded: false, buttonHidden: false, button: 'Show fewer' });
    assert.equal(el('demandListToggle').getAttribute('aria-expanded'), 'true');
    // New data arriving does not fold a list the reader has opened.
    assert.equal((await demand(14)).folded, false);
    vm.runInContext("toggleList('demandList')", context);
    assert.deepEqual(await demand(), { rows: 14, extra: 4, folded: true, buttonHidden: false, button: 'Show 4 more' });
    assert.deepEqual(await demand(10), { rows: 10, extra: 0, folded: true, buttonHidden: true, button: 'Show 0 more' });
    assert.deepEqual(await demand(40), { rows: 25, extra: 15, folded: true, buttonHidden: false, button: 'Show 15 more' });
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
    assert.match(el('topGamesList').innerHTML, /#140 .*Game 139/);
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
    const order = [...html.matchAll(/<a class="game-link"[^>]*>([^<]*)<\/a>/g)].map(match => match[1].trim());
    assert.deepEqual(order, ['Gitaroo Man', 'Silent Hill 2', 'Jak X', '&lt;img src=x onerror=alert(1)&gt;', 'Okami'],
        'surging first, then by mentions, quiet games last however often they were named; a broken entry is dropped');
    assert.match(el('pricesSummary').textContent, /not what anything sold for · 5 games · 1 surging$/);
    assert.equal(el('pricesEmpty').classList.contains('hidden'), true);
    assert.deepEqual([el('tabPricesCount').textContent, el('tabPricesCount').classList.contains('hidden')], ['5', false], 'the tab says how many games');

    assert.match(html, /<span class="level-tag level-surging" title="[^"]+">surging<\/span>/);
    assert.match(html, /<span class="level-tag level-dormant" title="[^"]+">quiet<\/span>/);
    // A row is the name (a link to the game's page), the US and UK medians and the cheapest euro one. Nothing else.
    assert.match(html, /<a class="game-link" href="#game=Silent%20Hill%202" onclick="return openGameLink\(event, &quot;Silent Hill 2&quot;\)"[^>]*>Silent Hill 2<\/a>/);
    assert.match(html, /<span class="ebay-quote" title="[^"]*"><span class="ebay-flag">US<\/span><b>\$220<\/b><\/span>/);
    assert.match(html, /<span class="ebay-quote is-stale" title="[^"]*"><span class="ebay-flag">UK<\/span><b>£105<\/b><\/span>/, 'a staple is checked every 6 hours, so 9 hours is overdue');
    assert.match(html, /<span class="ebay-quote" title="[^"]*"><span class="ebay-flag">US<\/span><b>\$34\.99<\/b><\/span>/, 'a quiet game is checked once a day, so 16 hours is not');
    assert.match(html, /<span class="ebay-note">no price yet<\/span>/, 'a game with no figure says so');
    assert.doesNotMatch(html, /<img/, 'titles are escaped');
    assert.equal((html.match(/<li /g) || []).length, (html.match(/class="price-links"/g) || []).length, 'every row keeps its eBay / PriceCharting search buttons');
    for (const detail of ['ebay-median', 'ebay-rest', 'few copies', 'copies', 'chart-open', 'in headlines', 'median · from', 'ebay-age', 'class="ebay-figures"']) {
        assert.ok(!html.includes(detail), `${detail} belongs on the game's page, not in the list`);
    }

    // No folding on this page: every game is listed, and the search box narrows them down.
    const many = { currencies: { US: '<b>', UK: 'GBP' }, games: Object.fromEntries(Array.from({ length: 8 }, (_, n) => [
        n === 3 ? 'Kingdom Hearts II' : `Game ${n}`,
        { level: 'normal', mentions: 8 - n, US: { checked: '2026-10-06T11:00Z', copies: 2, lowest: 9.5, median: 12, postage: 3 } }])) };
    const long = showPrices(many);
    const titles = (text) => [...text.matchAll(/<a class="game-link"[^>]*>([^<]*)<\/a>/g)].map(match => match[1].trim());
    assert.equal(titles(long).length, 8);
    assert.doesNotMatch(long, /list-extra/);
    assert.match(long, /<b>12\.00 &lt;b&gt;<\/b>/, 'a currency code the browser does not know is shown as text, never as markup');
    assert.doesNotMatch(long, /<b>(?!12\.00 &lt;b&gt;<\/b>)/);

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
    const figures = (title) => vm.runInContext(`compactPriceHtml(${JSON.stringify(title)}, __now, 'en-GB')`, context);

    // US, UK and the cheapest euro site: the names and medians, nothing else.
    const sites = (title) => [...figures(title).matchAll(/<span class="ebay-flag">([^<]+)<\/span><b>([^<]+)<\/b>/g)].map(match => `${match[1]} ${match[2]}`);
    assert.deepEqual(sites('Silent Hill 2'), ['US $220', 'UK £105']);
    assert.match(figures('Silent Hill 2'), /^<span class="ebay-quotes"><span class="ebay-quote" title="Median asking price on eBay US\./);
    assert.doesNotMatch(figures('Silent Hill 2'), /href=|copies|median ·|<a /, 'no links and no detail in the short form');
    // The feed's spelling finds the price file's.
    assert.deepEqual(sites('SILENT HILL 2'), ['US $220', 'UK £105']);
    assert.deepEqual(sites('Persona 4'), ['US $73.00'], "a pinned game's search words name it too; a site with nothing counted is left out");
    assert.deepEqual(sites('Shin Megami Tensei: Persona 4'), ['US $73.00']);
    assert.deepEqual(sites('Kingdom Hearts 2'), ['US $15.00', 'UK £8.00']);
    assert.deepEqual(sites('The Getaway'), ['UK £4.50']);
    assert.deepEqual(sites('Jak & Daxter: The Precursor Legacy'), ['US $11.00']);
    assert.deepEqual(sites('Gitaroo Man'), ['US $140']);
    assert.deepEqual(sites('Okami'), ['US $34.99']);
    assert.doesNotMatch(figures('Okami'), /is-stale/, 'a quiet game is checked once a day, so 16 hours is not overdue');
    assert.match(figures('Silent Hill 2'), /ebay-quote is-stale"[^>]*><span class="ebay-flag">UK/, 'a stale figure is dimmed');
    // Nothing is shown rather than something misleading.
    for (const title of ['Jak X', 'Silent Hill', 'Silent Hill 3', 'Black', 'Not In The File', '', null, undefined, 'constructor', '<img src=x onerror=alert(1)>']) {
        assert.equal(figures(title), '', `no figures for ${JSON.stringify(title)}`);
    }
    assert.doesNotMatch(figures('<b>Bold</b> Game'), /<b>Bold/);
    // Nothing from the price file reaches the page as markup.
    showPrices({ ...prices, currencies: { US: '"><img src=x onerror=alert(1)>', UK: 'GBP' } }, watchlist);
    const odd = figures('Kingdom Hearts II');
    assert.match(odd, /<b>15\.00 &quot;&gt;&lt;img src=x onerror=alert\(1\)&gt;<\/b>/);
    assert.doesNotMatch(odd, /<img|"">/);
    showPrices(prices, watchlist);

    // The cheapest euro site is the one whose median is lowest, and only one is shown.
    const euros = { ...prices, games: { 'Euro Game': { level: 'normal', mentions: 3,
        US: site(30), UK: site(20),
        DE: site(25), FR: site(18, { copies: 3 }), IT: site(12, { copies: 0 }), ES: { checked: '2026-10-06T11:00Z', unmatched: true } } } };
    euros.currencies = { US: 'USD', UK: 'GBP', DE: 'EUR', FR: 'EUR', IT: 'EUR', ES: 'EUR' };
    showPrices(euros);
    assert.deepEqual(sites('Euro Game'), ['US $30.00', 'UK £20.00', 'from FR €18.00'], 'a site with no copies or no match is not the cheapest');
    assert.match(figures('Euro Game'), /Lowest median asking price across the euro eBay sites: eBay FR/);
    vm.runInContext("fxData = { date: '2026-10-13', rates: { USD: 1.25, GBP: 0.8 } }; showEuro = true", context);
    try {
        assert.match(figures('Euro Game'), /from FR<\/span><b>€18\.00<\/b>/, 'the EUR button leaves euro figures alone');
        assert.match(figures('Euro Game'), /<b>≈€/, 'and converts the others');
    } finally { vm.runInContext('showEuro = false; fxData = null', context); }
    showPrices(prices, watchlist);

    // The game's own page holds the detail: every site with its figures, the chart, the eBay searches, the lookup chips.
    const gamePage = (title) => vm.runInContext(`gamePriceDetailHtml(${JSON.stringify(title)}, __now, 'en-GB')`, context);
    const rendered = (title) => { vm.runInContext(`renderGamePage(${JSON.stringify(title)})`, context); return el('gamePrices').innerHTML; };
    const page = gamePage('Silent Hill 2');
    assert.match(page, /<b class="ebay-median">\$220<\/b><span class="ebay-rest">median · from \$120 · 97<span title="[^"]*">\+<\/span> copies <span class="ebay-age" title="When eBay was last asked">· 2h ago<\/span>/);
    assert.match(page, /<b class="ebay-median">£105<\/b><span class="ebay-rest">median · from £52\.70 · 47 copies /);
    assert.match(page, /<span class="ebay-site is-stale"><span class="ebay-flag">UK<\/span>/, 'a staple is checked every 6 hours, so 9 hours is overdue');
    assert.match(page, /class="chart-open"/);
    assert.match(page, /class="price-links"/);
    assert.match(page, /href="https:\/\/www\.ebay\.com\/sch\/i\.html\?_nkw=Silent%20Hill%202%20ps2&amp;_sacat=139973&amp;LH_ItemCondition=2750%7C3000%7C4000%7C5000&amp;LH_BIN=1&amp;LH_PrefLoc=1"/);
    assert.match(page, /href="https:\/\/www\.ebay\.co\.uk\/sch\/i\.html\?_nkw=Silent%20Hill%202%20ps2/);
    assert.match(gamePage('Gitaroo Man'), /\$140<\/b><span class="ebay-rest">median · from \$140 · 1 copy <span class="level-tag few-copies"[^>]*>few copies<\/span>/);
    assert.match(gamePage('Jak X'), /search needs tuning<\/span> <span class="ebay-age"/, 'unmatched is not shown as zero copies');
    assert.match(gamePage('Jak X'), /<span class="ebay-note">none listed<\/span>/);
    assert.match(rendered('Black'), /Not priced on eBay yet/);
    assert.match(gamePage('Black'), /class="price-links"/, 'an unpriced game still has its lookup links');
    assert.doesNotMatch(gamePage('<b>Bold</b> Game'), /<b>Bold/);

    // The places a game's name appears: Most Mentioned Games, the table, the Demand Index
    // and the games named in the last day.
    const item = (game) => ({ headline: `${game} news`, source: 'Eurogamer', link: 'https://e.example/', matched_game: game, sentiment: 50, timestamp: '2026-10-01 10:00 UTC' });
    context.__games = [item('Persona 4'), item('Persona 4'), item('Black'), { ...item(''), matched_game: null }];
    vm.runInContext('renderTopGames(__games)', context);
    const rows = el('topGamesList').innerHTML.split('<li ').slice(1);
    assert.equal(rows.length, 2);
    assert.match(rows[0], /#1 <a class="game-link"[^>]*>Persona 4<\/a>[\s\S]*<span class="ebay-quotes">/, 'the name opens the game, then the short prices');
    assert.match(rows[0], /<span class="ebay-quotes">[\s\S]*<span class="price-links"/, 'short prices first, then the eBay / PriceCharting search buttons');
    assert.match(rows[1], /#2 <a class="game-link"[^>]*>Black<\/a>/);
    assert.doesNotMatch(rows[1], /ebay-quotes/, 'a game that is not priced has no prices');
    assert.match(rows[1], /class="price-links"/, 'but it keeps its search buttons');

    vm.runInContext('renderTable(__games)', context);
    const cells = el('feedTableBody').children.map(row => row.innerHTML.match(/<td data-col="game"[\s\S]*?<\/td>/)[0]);
    assert.deepEqual(cells.map(cell => /ebay-quotes/.test(cell)), [true, true, false, false]);
    assert.match(cells[0], />Persona 4<\/a><span class="ebay-quotes">/);

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
    assert.match(named[0], /<a class="game-open" href="#game=Persona%204"[^>]*aria-label="Open the page for Persona 4"/, 'the filter button stays; a small link opens the game');
    assert.match(named[0], /<span class="ebay-quotes">[\s\S]*<span class="price-links"/);

    // No price file: every list looks as it did before prices existed.
    showPrices(null);
    vm.runInContext(`renderTopGames(__games); renderTable(__games); renderRecentGames(__games, ${noon})`, context);
    assert.doesNotMatch(el('topGamesList').innerHTML + el('todayList').innerHTML + el('feedTableBody').children.map(row => row.innerHTML).join(''), /ebay-quote/);
    assert.equal(figures('Silent Hill 2'), '');

    const css = read('retro.css');
    assert.doesNotMatch(css, /\.ebay-quote\.is-stale b \{ opacity/, 'a price beside a name is never greyed');
});

await check('every game name in a list opens the game\'s own page, and prices load there', () => {
    showPrices(samplePrices());
    const link = (title) => vm.runInContext(`gameLinkHtml(${JSON.stringify(title)})`, context);
    assert.match(link('Silent Hill 2'), /^<a class="game-link" href="#game=Silent%20Hill%202" onclick="return openGameLink\(event, &quot;Silent Hill 2&quot;\)"/);
    const hostile = link('"><img src=x onerror=alert(1)>\'');
    assert.doesNotMatch(hostile, /<img/);
    assert.doesNotMatch(hostile, /onerror=alert\(1\)>'/);
    assert.match(hostile, /href="#game=%22%3E%3Cimg/);
    // A plain click opens the page here; a modified click is left to the browser (new tab).
    context.__evt = { ctrlKey: false, metaKey: false, shiftKey: false, button: 0 };
    assert.equal(vm.runInContext("openGameLink(__evt, 'Okami')", context), false);
    assert.match(el('gameTitle').textContent, /^Okami$/);
    assert.equal(el('viewGame').classList.contains('hidden'), false);
    for (const key of ['ctrlKey', 'metaKey', 'shiftKey']) {
        context.__evt = { ctrlKey: false, metaKey: false, shiftKey: false, button: 0, [key]: true };
        assert.equal(vm.runInContext("openGameLink(__evt, 'Okami')", context), true, `${key} click is the browser's`);
    }
    // The page holds what the lists no longer do.
    assert.match(el('gamePrices').innerHTML, /class="ebay-figures"/);
    assert.match(el('gamePrices').innerHTML, /class="chart-open"/);
    assert.match(el('gamePrices').innerHTML, /class="price-links"/);
    assert.match(read('guide.html'), /game page|page of its own/i, 'the guide explains the game pages');
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
    // A steady figure is checked every 48 hours, so it is overdue only after 56.
    assert.equal(evalJson("staleFor({ steady: true }, 8)"), 56);
    assert.equal(evalJson("staleFor({ steady: true }, 30)"), 56);
    assert.equal(evalJson("staleFor({ steady: true }, 3)"), 56);
    assert.equal(evalJson("staleFor({ steady: 'yes' }, 8)"), 8, 'only true counts');
    assert.equal(evalJson("staleFor({}, 8)"), 8);
    assert.equal(evalJson("staleFor(null, 8)"), 8);
    assert.deepEqual(evalJson('Object.fromEntries(Object.entries(LEVELS).map(([name, level]) => [name, level.stale]))'),
        { surging: 3, staple: 8, normal: 8, dormant: 30, underrated: 30, rare: 30 }, 'the rarest games are checked daily, like quiet ones');
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
        [['data/prices/latest.json', 'GET', []], ['ebay_watchlist.json', 'GET', []], ['data/prices/index.json', 'GET', []]]);
    assert.equal(el('indexSection').classList.contains('hidden'), true, 'no index file: no index');
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
    const figure = (title) => vm.runInContext(`compactPriceHtml(${JSON.stringify(title)}) !== ''`, context);
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

    assert.match(read('index.html'), /await loadPrices\(\);\s*await loadRare\(\);\s*await loadDemand\(\);\s*await loadDigitalArchive\(\);\s*refreshDashboard\(\);/,
        'prices are loaded before the lists that show them');
});

await check('four pages in one: Tracker, Rarest, Most mentioned and eBay prices', () => {
    const views = { dashboard: ['viewDashboard', 'tabDashboard'], rare: ['viewRare', 'tabRare'], mentions: ['viewMentions', 'tabMentions'], prices: ['viewPrices', 'tabPrices'] };
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
    assert.equal(selected(), 'false false false true', 'a screen reader hears which tab is open');
    assert.equal(show('prices'), 'prices');
    assert.equal(show('mentions'), 'mentions');
    assert.equal(selected(), 'false false true false');
    assert.equal(show('rare'), 'rare');
    assert.equal(selected(), 'false true false false');
    assert.equal(show('dashboard'), 'dashboard');
    assert.equal(selected(), 'true false false false');
    assert.equal(show('dashboard'), 'dashboard');
    assert.deepEqual(addressChanges, ['#prices', '#mentions', '#rare', '/'],
        'each change of page is one new entry in the history, so Back returns to the last page and the address can be bookmarked');
    for (const name of ['nonsense', 'constructor', 'toString', '', null]) assert.equal(show(name), 'dashboard', `"${name}" is not a page`);
    assert.deepEqual(addressChanges, ['#prices', '#mentions', '#rare', '/'], 'staying on a page adds nothing to the history');
    // Leaving a part of the Tracker that the address names ("#sourcesSection") by its own tab clears the name.
    context.location.hash = '#sourcesSection';
    assert.equal(show('dashboard'), 'dashboard');
    assert.deepEqual(addressChanges, ['#prices', '#mentions', '#rare', '/', '/']);

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
    assert.equal(arrive('#rare'), 'rare');
    for (const hash of ['', '#', '#dashboard', '#constructor', '#__proto__']) assert.equal(arrive(hash), 'dashboard', `"${hash}" opens the Tracker`);
    assert.deepEqual(addressChanges, [], 'reading the address never rewrites it');
    context.location.hash = '';

    const page = read('index.html');
    const at = (text) => { const index = page.indexOf(text); assert.notEqual(index, -1, text); assert.equal(page.indexOf(text, index + 1), -1, `${text} appears once`); return index; };
    const order = ['id="tabDashboard"', 'id="tabRare"', 'id="tabDemand"', 'id="tabMentions"', 'id="tabPrices"',
        '<div id="viewDashboard" role="tabpanel" aria-labelledby="tabDashboard" class="space-y-8">', 'id="feedSection"', 'id="sourcesSection"',
        '<div id="viewRare" role="tabpanel" aria-labelledby="tabRare" class="hidden ', 'id="rareSection"',
        '<div id="viewDemand" role="tabpanel" aria-labelledby="tabDemand" class="hidden ', 'id="demandSection"',
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
    // Phone: seven tabs slide sideways instead of squeezing into one another.
    assert.match(read('retro.css'), /body \.view-tabs \{[^}]*flex-wrap: nowrap;[^}]*overflow-x: auto/);
    assert.match(read('retro.css'), /body \.view-tab \{ flex: 1 0 auto;[^}]*white-space: nowrap/);
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

await check('forums and 4chan boards: their rows, and adding one', () => {
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

    assert.equal(el('statTotalItems').innerText, 3);
    assert.match(el('topGamesList').innerHTML, /#1 <a[^>]*>Ico<\/a>[\s\S]*#2 <a[^>]*>Okami<\/a>/, 'both count as mentions');

    const [, forumRow, boardRow] = rows();
    assert.match(forumRow, /fa-solid fa-comments[^>]*title="Forums"><\/i>Forum: /);
    assert.match(forumRow, /href="https:\/\/forum\.example\/threads\/ico\.1\/"[^>]*>\s*Thread /);
    // 4chan asks that it be named as the source and linked to.
    assert.match(boardRow, /fa-solid fa-user-secret[^>]*title="4chan"><\/i>4chan \/vr\//);
    assert.match(boardRow, /Thread on \/vr\/ naming Okami/);
    assert.match(boardRow, /href="https:\/\/boards\.4chan\.org\/vr\/thread\/101"[^>]*>\s*Thread /);
    for (const row of [forumRow, boardRow]) assert.doesNotMatch(row, /data-col="score"|score-value|Source weight/, 'no sentiment and no weight on a row');

    // The feed can be narrowed to either kind.
    const only = (kind) => { el('typeSelect').value = kind; vm.runInContext('filterFeedItems()', context); return rows().length; };
    assert.deepEqual([only('4chan'), only('forum'), only('news'), only('all')], [1, 1, 1, 3]);
    const page = read('index.html');
    assert.match(page, /<option value="forum">Forums<\/option>\s*<option value="4chan">4chan<\/option>/);

    // Sources: a tab for each, with the board's own page as its link.
    vm.runInContext("setSourceTab('4chan')", context);
    let html = el('sourcesView').innerHTML;
    assert.equal((html.match(/<tr data-index=/g) || []).length, feeds.sources.filter(src => src.type === '4chan').length);
    assert.match(html, /<a href="https:\/\/boards\.4chan\.org\/vr\/"[^>]*>\/vr\/ - Retro Games<\/a>/);
    assert.doesNotMatch(html, /data-field="weight"|data-col="weight"/, 'there are no weights to set');
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

    // Yellow has few jobs: a price figure, and the keepsake colour of the collection button and badges. The shop buttons have their own colours since 2026-10-16.
    const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(m => [m[1].trim(), m[2]]);
    const yellow = rules.filter(([, body]) => /var\(--money/.test(body)).map(([selector]) => selector);
    assert.ok(yellow.length >= 2, 'at rest and under the pointer');
    assert.ok(yellow.every(selector => selector.split(',').every(part => /\.(?:price-link|shelf-quote|brand-btn-collection|coll-badge-qty)\b|\.coll-count/.test(part))), yellow.join(' | '));
    assert.match(css, /body \.price-link:hover, body \.price-link:focus-visible \{\s*background: var\(--money\);\s*border-color: var\(--money\);\s*color: var\(--bg\);/);
    // ...by no other route either: every colour is named once, at the top, and the strip's
    // yellow is used by the strip alone; the pages have no yellow of their own.
    const afterTokens = css.slice(css.indexOf('}', css.indexOf(':root {')) + 1).replace(/\/\*[\s\S]*?\*\//g, '');
    assert.deepEqual(afterTokens.match(/#[0-9A-Fa-f]{3,8}\b/g), null, 'no colour written out below the list at the top');
    assert.deepEqual(rules.filter(([, body]) => /var\(--strip-/.test(body)).map(([selector]) => selector),
        ['body .brand-bar::before', 'body .stat:nth-child(1)::before', 'body .stat:nth-child(2)::before', 'body .stat:nth-child(3)::before']);
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
    // Red marks remaster news (the tag, the number at the top, the open page's line).
    assert.match(css, /body \.remaster-tag \{ border-color: var\(--red-line\); border-radius: 4px; color: var\(--red\); \}/);
    assert.match(css, /body \.stat-value\.is-news \{ color: var\(--red\); \}/);
    // Teal is live and well: the sync dot, the active feeds.
    assert.match(css, /body \.brand-dot \{[^}]*background: var\(--green\)/);
    assert.match(css, /body \.stat-value\.is-live \{ color: var\(--green\); \}/);
    assert.match(page, /<div id="statRemasters" class="stat-value is-news">/);
    assert.match(page, /<div id="statFeedsCount" class="stat-value is-live">/);
    assert.doesNotMatch(page, /statAvgSentiment|Net sentiment|SENTIMENT<\/th>|score-meter/, 'no sentiment on the page');
    // The tag in the table, beside a game's rank and beside a game named today and on a game's own page is the same tag.
    assert.equal((script.match(/<span class="remaster-tag /g) || []).length, 4);
    context.__items = [{ headline: 'Okami HD announced', source: 'Eurogamer', link: 'https://e.example/okami', matched_game: 'Okami',
        is_remaster_rumor: true, sentiment: 50, timestamp: '2026-10-07 08:00 UTC' }];
    vm.runInContext('allFeedData = __items; refreshDashboard();', context);
    assert.match(el('feedTableBody').children[0].innerHTML, /<span class="remaster-tag border [^"]*">Remaster<\/span>\s*Okami HD announced/);
    assert.match(el('topGamesList').innerHTML, /<span class="remaster-tag [^"]*">1 remaster<\/span>/);

    // All four meet in the strip across the top of both pages, and in the mark.
    assert.match(css, /body \.brand-bar::before \{\s*content: "";\s*display: block;\s*height: 4px;\s*background: linear-gradient\(90deg,\s*var\(--strip-red\) 0 25%, var\(--strip-yellow\) 25% 50%, var\(--strip-teal\) 50% 75%, var\(--strip-blue\) 75% 100%\);\s*\}/);
    assert.deepEqual(named('.brand-bar'), ['body .brand-bar', 'body .brand-bar', 'body .brand-bar::before']);
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
    assert.equal((guide.match(/shop buttons/g) || []).length, 3);

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
    // The shelf above the tabs: the six most-named games as box art, from the same list, links to their pages
    const shelf = el('shelf').innerHTML;
    assert.equal(shelf.split('<li class="shelf-item">').length - 1, 10, 'every game of the list, up to 24');
    // The arrows: the row moves by most of its width; one with nowhere to go is off; both hide when everything fits
    const strip = el('shelf'); Object.assign(strip, { clientWidth: 600, scrollWidth: 2000, scrollLeft: 0 });
    let moved = null; strip.scrollBy = ({ left }) => { moved = left; strip.scrollLeft += left; };
    vm.runInContext('shelfScroll(1)', context);
    assert.equal(moved, 510, 'a screenful less a little');
    assert.equal(el('shelfPrev').disabled, false); assert.equal(el('shelfNext').disabled, false);
    strip.scrollLeft = 1400; vm.runInContext('updateShelfArrows()', context);
    assert.equal(el('shelfNext').disabled, true, 'at the end');
    strip.scrollLeft = 0; vm.runInContext('updateShelfArrows()', context);
    assert.equal(el('shelfPrev').disabled, true, 'at the start');
    strip.scrollWidth = 600; vm.runInContext('updateShelfArrows()', context);
    assert.equal(el('shelfPrev').classList.contains('hidden') && el('shelfNext').classList.contains('hidden'), true, 'everything fits: no arrows');
    assert.match(shelf, /<a class="shelf-link" href="#game=Okami"[^>]*aria-label="Okami: 5 mentions in the last 24 hours"/);
    assert.ok(shelf.indexOf('>Okami<') < shelf.indexOf('>Ico<') && shelf.indexOf('>Ico<') < shelf.indexOf('>Mixed Game<'), 'the order of the list');
    assert.match(shelf, /<span class="shelf-count">5<\/span>/);
    assert.match(shelf, /Ratchet &amp; Clank|^(?!.*Ratchet & Clank <3)/s, 'names are escaped');
    assert.doesNotMatch(shelf, /<3/, 'a name is never markup');
    assert.doesNotMatch(page, /Letterboxd/i, 'the page does not carry the theme\'s brand name');
    const rows = el('todayList').innerHTML.split('<li ').slice(1);
    assert.equal(rows.length, 10);
    assert.match(rows[0], /onclick="showGameRows\(0\)"[^>]*class="recent-game text-cyan-300 font-bold">Okami<\/button><a class="game-open"[^>]*><i [^>]*><\/i><\/a> <span class="remaster-tag [^"]*">1 remaster<\/span>/);
    assert.match(rows[0], />5 mentions<\/span>/);
    assert.match(rows[1], /class="recent-game text-cyan-300">Ico<\/button>/, 'only the first name is bold');
    assert.match(rows[0], /Eurogamer · r\/ps2 · YouTube: Some Channel <span class="text-slate-500">\+1 more<\/span>/, 'three sources named, the rest counted');
    assert.match(rows[2], />Mixed Game<\/button>(?:<a class="game-open"[^>]*><i [^>]*><\/i><\/a>)?<\/span>\s*<span[^>]*>3 mentions<\/span>/, 'the count is of every mention, headline or text');
    assert.match(rows[4], />Kuon<\/button>(?:<a class="game-open"[^>]*><i [^>]*><\/i><\/a>)?<\/span>\s*<span[^>]*>1 mention<\/span>/);
    assert.match(rows[4], /4chan \/vr\//);
    assert.match(rows[9], />Retro<\/button><a class="game-open"[^>]*><i [^>]*><\/i><\/a> <span class="[^"]*" title="Named in the text under a headline, not in the headline itself\. These are wrong more often\.">in the text only<\/span>/);
    assert.match(rows[9], />2 mentions<\/span>/);
    assert.doesNotMatch(rows.slice(0, 9).join(''), /in the text only/);
    assert.ok(rows.every(html => /class="game-open"/.test(html)), 'every game has a link to its page');
    assert.ok(rows.every(html => /class="price-links"/.test(html)), 'every game carries its search buttons');
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
        ['body .recent-game', 'background: transparent; border: 0; padding: 0; text-align: left; cursor: pointer; font-family: var(--serif); font-weight: 700; font-size: .98rem;'],
        ['body .recent-game:hover, body .recent-game:focus-visible', 'text-decoration: underline; text-underline-offset: 3px;'],
        ['body #feedSummary .recent-game', 'min-height: 2.1rem; vertical-align: middle;'],
        ['body #todayList > li > div:first-child, body #demandList > li > div:first-child, body #topGamesList > li > div:first-child, body #pricesList > li > div:first-child',
            'flex-wrap: wrap; row-gap: .25rem; font-size: .8125rem;'],
    ]);
    assert.match(css, /body main button, body main a\.bg-slate-800, body main \.from-blue-600 \{\s*min-height: 2\.75rem;/);
    // Everything the stylesheet hides. A rule added here on purpose belongs in this list; one
    // that hides the new list or the line over the table by where it sits does not.
    assert.deepEqual([...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(rule => /display:\s*none|visibility:\s*hidden/.test(rule[2])).map(rule => rule[1].replace(/\s+/g, ' ').trim()), [
        'body .view-tab.hidden', 'body .is-folded > .list-extra', 'body .view-tab i, body .view-tab-count:not(.hidden)', 'body .price-links::-webkit-scrollbar', 'body #feedSection thead',
        'body #feedTableBody td[data-col="game"][data-unmatched]', 'body #sourceTabs::-webkit-scrollbar', 'body .sources-table > thead', 'body .sources-table td[data-col="remove"]:empty',
        'body .chart-tools::-webkit-scrollbar', 'body .shelf::-webkit-scrollbar', 'body .shelf-arrow.hidden',
    'body .library-add.hidden',
    ]);

    // The list sits first on the Tracker, above the Demand Index and the table.
    const order = ['class="stat-strip"', 'id="todaySection"', 'id="feedSection"'].map(mark => page.indexOf(mark));
    assert.ok(order.every((at, i) => at > 0 && (i === 0 || at > order[i - 1])), order.join(' '));
    assert.match(page, /<div id="todaySection" class="[^"]*bg-ps2card[^"]*">\s*<div class="lb-section-header">\s*<div>\s*<h2>Named in the last 24 hours<\/h2>\s*<p id="todaySummary" class="text-xs text-slate-400 mt-1">Loading\.\.\.<\/p>/);
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
    assert.match(page, /<option value="matched" selected>PS2 Games Only<\/option>\s*<option value="remaster">Remaster News Only<\/option>\s*<option value="all">Everything<\/option>\s*<option value="digital">Digital-Only News<\/option>\s*<\/select>/);
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
    assert.match(cell('r/ps2 item 2'), /text-cyan-300"><a class="game-link"[^>]*>Okami<\/a>[\s\S]*<div class="[^"]*">also names Ico<\/div>/);
    assert.match(cell('Gematsu item 16'), />Zeta Game<[\s\S]*also names Alpha Game</);
    assert.doesNotMatch(cell('Eurogamer item 1'), /also names/);
    assert.match(cell('Polygon item 13'), /data-unmatched[^>]*><span class="text-slate-500">Unmatched \/ General<\/span>/);
    context.__crowd = [row('r/ps2', 1, ['A<1>', 'B<2>', 'C3', 'D4', 'E5', 'F6', 'The G7 Saga', 'G7 Two'])];
    vm.runInContext('visibleFeedData = __crowd; filterFeedItems();', context);
    assert.match(tableRows()[0].innerHTML, /text-cyan-300"><a class="game-link"[^>]*>A&lt;1&gt;<\/a>[\s\S]*also names B&lt;2&gt;, C3, D4, E5 and 3 more<\/div>/);
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
    assert.match(cell('r/ps2 item 2'), /text-cyan-300"><a class="game-link"[^>]*>Ico<\/a>[\s\S]*also names Okami</, 'the game asked for leads its rows');
    assert.match(cell('r/ps2 item 2'), /href="#game=Ico"/);
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
    assert.match(ranked[0], /#1 <a[^>]*>Okami<\/a>[\s\S]*>5 mentions · 23%</);
    assert.match(ranked.find(html => />Ico<\/a>/.test(html)), />2 mentions · 9\.1%</, 'named second in one item, first in another');
    assert.ok(ranked.some(html => />Alpha Game<\/a>/.test(html)), 'a game only ever named second is ranked too');

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

    // The change beside each median is on the game's page; the list keeps only the short form.
    const detail = (name) => vm.runInContext(`gamePriceDetailHtml(${JSON.stringify(name)}, ${now}, 'en-GB')`, context);
    assert.doesNotMatch(rows.join(''), /ebay-change/, 'no week change in the list');
    assert.match(detail('Persona 4'), /<b class="ebay-median">£73\.49<\/b> <span class="ebay-change is-up" title="A week before \((?:7 Oct|Oct 7)\) the median was £71\.19: up £2\.30, 3\.2%\.">\(£2\.30 ▲ 3\.2%\)<\/span>/);
    assert.match(detail('Dear UK'), /<b class="ebay-median">£80\.00<\/b> <span class="ebay-change" title="A week before \((?:7 Oct|Oct 7)\) the median was £80\.00: the same\.">\(no change\)<\/span>/);
    assert.match(detail('Also Dear UK'), /<b class="ebay-median">£80\.00<\/b><span class="ebay-rest">/, 'no figure from a week before: nothing in brackets');
    assert.match(detail('Cheap UK'), /<b class="ebay-median">£5\.00<\/b> <span class="ebay-change is-up"[^>]*>\(£1\.00 ▲ 25%\)<\/span>/);
    assert.match(detail('Dollars Only'), /<b class="ebay-median">\$200<\/b> <span class="ebay-change is-down" title="A week before \((?:7 Oct|Oct 7)\) the median was \$250: down \$50\.00, 20%\.">\(\$50\.00 ▼ 20%\)<\/span>/);

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
    // Until a game has a week of history it is compared with its oldest check, and the hint says how many days that is.
    assert.match(change(12, { checked: '2026-10-11T10:00Z', median: 10 }), /title="3 days before \(/, 'a three-day-old base is called that');
    assert.match(change(12, { checked: '2026-10-07T10:00Z', median: 10 }), /title="A week before \(/, 'seven days is a week');
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

    // The median of complete copies, when some copies say they are not complete.
    const siteLine = (site) => {
        context.__site = { checked: '2026-10-14T10:00Z', lowest: 20, median: 30, ...site };
        return vm.runInContext("priceSiteHtml('UK', __site, 'GBP', Date.parse('2026-10-14T11:00Z'), 'en-GB', 48)", context);
    };
    assert.match(siteLine({ copies: 5, complete: { copies: 3, median: 42 } }),
        /5 copies · <span class="ebay-complete" title="Median of the 3 copies whose listing[^"]*">complete £42\.00 \(3\)<\/span> <span class="ebay-age"/);
    for (const bad of [undefined, null, 'x', {}, { copies: 5, median: 42 }, { copies: 3, median: '42' }, { copies: 0, median: 42 },
        { copies: 1.5, median: 42 }, { copies: 3, median: Infinity }]) {
        assert.doesNotMatch(siteLine({ copies: 5, complete: bad }), /ebay-complete/, JSON.stringify(bad));
    }
    // New and sealed copies are shown apart from the used figures: after them, or alone when no used copy is listed.
    assert.match(siteLine({ copies: 0, median: null, lowest: null, new: { copies: 3, lowest: 800, median: 875 } }),
        /none listed<\/span> · <span class="ebay-new" title="3 new or sealed copies are listed[^"]*">new from £800 \(3\)<\/span> <span class="ebay-age"/);
    assert.match(siteLine({ copies: 5, new: { copies: 1, lowest: 700, median: 700 } }),
        /5 copies · <span class="ebay-new" title="1 new or sealed copy is listed[^"]*">new from £700 \(1\)<\/span>/);
    // Used copies listed from abroad: a number of their own when none is listed at home, never beside a real median.
    const abroadLine = siteLine({ copies: 0, median: null, lowest: null, abroad: { copies: 27, lowest: 300, median: 450 },
        new: { copies: 3, lowest: 800, median: 875 } });
    assert.match(abroadLine, /<b class="ebay-median ebay-abroad">£450<\/b><span class="ebay-rest">median from abroad · 27 copies listed in other countries, none in this one · <span class="ebay-new"/);
    assert.doesNotMatch(abroadLine, /none listed/);
    assert.doesNotMatch(siteLine({ copies: 5, abroad: { copies: 27, lowest: 300, median: 450 } }), /abroad/, 'a site with copies at home shows its own median');
    for (const bad of [undefined, null, 'x', {}, { copies: 0, median: 5 }, { copies: 2, median: '5' }, { copies: 2 }, { copies: 1.5, median: 5 }, { copies: 2, median: Infinity }]) {
        assert.doesNotMatch(siteLine({ copies: 0, median: null, abroad: bad }), /ebay-abroad/, JSON.stringify(bad));
    }
    for (const bad of [undefined, null, 'x', {}, { copies: 0, lowest: 5 }, { copies: 2, lowest: '5' }, { copies: 2 }, { copies: 1.5, lowest: 5 }, { copies: 2, lowest: Infinity }]) {
        assert.doesNotMatch(siteLine({ copies: 5, new: bad }), /ebay-new/, JSON.stringify(bad));
    }
    assert.doesNotMatch(siteLine({ copies: 0, median: null, lowest: null }), /ebay-new/, 'no new copies, nothing said');
    assert.match(siteLine({ copies: 2 }), /2 copies <span class="level-tag few-copies" title="Only 2 copies are for sale/);
    assert.doesNotMatch(siteLine({ copies: 3 }), /few-copies/);

    // The game's page: the change sits beside the median, the rest of the line as before.
    showPrices(prices);
    const gameDetail = (name) => vm.runInContext(`gamePriceDetailHtml(${JSON.stringify(name)}, ${now}, 'en-GB')`, context);
    const persona = gameDetail('Shin Megami Tensei: Persona 4');
    assert.match(persona, /<span class="ebay-site"><span class="ebay-flag">UK<\/span><span class="ebay-now"><b class="ebay-median">£73\.49<\/b> <span class="ebay-change is-up"[^>]*>\(£2\.30 ▲ 3\.2%\)<\/span><\/span><span class="ebay-rest">median · from £36\.75/);
    const plain = gameDetail('Also Dear UK');
    assert.match(plain, /<span class="ebay-flag">UK<\/span><b class="ebay-median">£80\.00<\/b><span class="ebay-rest">/);

    // Without prices the list keeps its usual order and says nothing about prices.
    vm.runInContext(`setPrices(null, null); renderRecentGames(__items, ${now})`, context);
    assert.deepEqual(evalJson('recentGameNames'), ['Unpriced Hit', 'Cheap UK', 'Few Dollars', 'Dear UK', 'Dollars Only', 'Also Dear UK', 'Persona 4', 'Retro']);
    assert.doesNotMatch(el('todaySummary').textContent, /expensive/);
    assert.doesNotMatch(el('todayList').innerHTML, /ebay-change/);

    const css = read('retro.css');
    assert.match(css, /body \.ebay-change \{ font-size: \.72rem; font-weight: 400; color: var\(--dim\); white-space: nowrap; \}\nbody \.ebay-change\.is-up \{ color: var\(--green\); \}\nbody \.ebay-change\.is-down \{ color: var\(--red\); \}\n\/\* On the detail page an overdue figure is dimmed, and so is how it moved \*\/\nbody \.ebay-site\.is-stale \.ebay-change \{ opacity: \.5; \}/);
    vm.runInContext('allFeedData = []; visibleFeedData = []; refreshDashboard();', context);
});

await check('the Rarest page: two lists of the rarest games, each with its own site\'s median', async () => {
    const rareFile = JSON.parse(read('rare_games.json'));
    const now = Date.parse('2026-10-08T12:00:00Z');
    const site = (median, copies = 3) => ({ checked: '2026-10-08T09:00Z', copies, lowest: median - 5, median });
    const prices = {
        currencies: { US: 'USD', UK: 'GBP' },
        games: {
            'Sengoku Anthology': { level: 'rare', mentions: 0, sites: ['UK'], UK: site(410) },
            'Fatal Frame 2: Crimson Butterfly': { level: 'normal', mentions: 2, UK: site(55), US: site(150) },
            Kuon: { level: 'normal', mentions: 1, UK: site(300), US: site(900) },
        },
        rare: { PAL: { 'Sengoku Anthology': 'Sengoku Anthology', 'Project Zero 2: Crimson Butterfly': 'Fatal Frame 2: Crimson Butterfly' },
                US: { 'Fatal Frame II: Crimson Butterfly': 'Fatal Frame 2: Crimson Butterfly' } },
    };
    context.__rare = rareFile;
    context.__rarePrices = prices;
    const draw = (region) => {
        vm.runInContext(`setPrices(__rarePrices, null); rareRegion = ${JSON.stringify(region)}; renderRare(__rare, ${now}, 'en-GB')`, context);
        return el('rareList').innerHTML.split('<li ').slice(1);
    };
    const rowOf = (rows, title) => rows.find(html => new RegExp(`#\\d+ ${esc(title).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}[< ]`).test(html));

    const pal = draw('PAL');
    const palCount = rareFile.lists.PAL.length;
    assert.equal(pal.filter(html => html.includes('class="rare-pc"')).length, palCount, 'every PAL row has a PriceCharting link');
    assert.match(pal[0], /pricecharting\.com\/search-products[^"]*pal%20playstation%202/, 'the PAL list searches the PAL page');
    assert.equal(pal.length, palCount);
    assert.equal(pal.filter(html => html.includes('list-extra')).length, palCount - 25, 'twenty-five shown, the rest a click away');
    const sengoku = rowOf(pal, 'Sengoku Anthology');
    assert.match(sengoku, /#2 Sengoku Anthology/);
    assert.match(sengoku, /guide \$860/);
    assert.match(sengoku, /<span class="ebay-flag">UK<\/span><b class="ebay-median">£410<\/b>/, 'its own site\'s median');
    assert.doesNotMatch(sengoku, /ebay-flag">US/, 'and only that site');
    assert.match(sengoku, /Sources: <a href="https:\/\/www\.pricecharting\.com\/[^"]*"[^>]*>pricecharting\.com<\/a>, <a [^>]*>racketboy\.com<\/a>/);
    assert.match(pal[0], new RegExp(`#1 ${esc(rareFile.lists.PAL[0].title)}`), 'in the order of the file');
    assert.match(rowOf(pal, 'Project Zero 2: Crimson Butterfly'), /£55\.00/, 'the price job says which game holds the figures');
    assert.match(rowOf(pal, 'Project Zero 2: Crimson Butterfly'), /US name: Fatal Frame II: Crimson Butterfly/);
    assert.match(rowOf(pal, 'Kuon'), /£300/, 'without a word from the price job, the game of the same name');
    assert.match(rowOf(pal, 'Gun Club'), /not priced/, 'the price job has the list and left this one out');
    assert.match(rowOf(pal, 'Ocean Commander'), /not priced/);
    const mapping = prices.rare;
    context.__rarePrices.rare = undefined;
    assert.match(rowOf(draw('PAL'), 'Gun Club'), /not checked yet/, 'before the price job has seen the list');
    context.__rarePrices.rare = mapping;
    draw('PAL');
    assert.match(rowOf(pal, 'Cart Kings'), /title="Released for India[^"]*">India<\/span>/);
    assert.equal(evalJson("document.getElementById('rareRegionPAL').getAttribute('aria-pressed')"), 'true');
    assert.equal(el('rareSummary').textContent, `${palCount} PAL games, rarest first by what a complete copy sells for (PriceCharting, 9 Oct 2026). Prices: eBay UK today · 3 with copies for sale`);

    const us = draw('US');
    assert.equal(us.length, rareFile.lists.US.length);
    assert.match(us[0], /#1 Kuon/);
    assert.match(us[0], /<span class="ebay-flag">US<\/span><b class="ebay-median">\$900<\/b>/);
    assert.match(rowOf(us, 'Fatal Frame II: Crimson Butterfly'), /\$150/);
    assert.equal(evalJson("document.getElementById('rareRegionUS').getAttribute('aria-pressed')"), 'true');
    vm.runInContext("showRareRegion('constructor')", context);
    assert.equal(evalJson('rareRegion'), 'PAL', 'only the two lists');

    // A hostile file is text, never markup, and only https sources are links.
    context.__hostile = { checked: 'soon', lists: { PAL: [null, { title: '<img src=x onerror=alert(1)>', rank: '<b>', note: '<script>',
        other_title: '<i>', flags: ['weak', '__proto__'], value_usd: { cib: 'lots' },
        evidence: [{ source: 'javascript:alert(1)', figure: 'x', date: 'y' }, { source: 'https://example.com/a"b', figure: '<b>', date: '"' }] }] } };
    vm.runInContext(`renderRare(__hostile, ${now}, 'en-GB')`, context);
    const hostile = el('rareList').innerHTML;
    assert.doesNotMatch(hostile, /<img|<script|<i>|javascript:|<b>/);
    assert.match(hostile, /#1 &lt;img/, 'a rank that is not a number gives way to the position');
    assert.doesNotMatch(hostile, /guide/);
    assert.equal((hostile.match(/<a /g) || []).length, 2, "its source link and the PriceCharting search");
    assert.equal((hostile.match(/rare-flag/g) || []).length, 1);
    assert.doesNotMatch(el('rareSummary').textContent, /PriceCharting,/, 'no date that is not a date');

    // Loading: a missing file, a hiccup with a list on screen, a file that is not JSON.
    const real = context.fetch;
    let answer = 404;
    context.fetch = async (path) => {
        assert.ok(['rare_games.json', 'rare_consoles.json'].includes(path), path);
        if (path === 'rare_consoles.json') return { ok: false, status: 404, json: async () => ({}) };
        if (answer === 'drop') throw new TypeError('Failed to fetch');
        if (answer === 'garbage') return { ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token'); } };
        if (typeof answer === 'number') return { ok: false, status: answer, json: async () => ({}) };
        return { ok: true, status: 200, json: async () => answer };
    };
    try {
        await vm.runInContext('loadRare()', context);
        assert.equal(el('rareSummary').textContent, 'No list of rare games yet.');
        answer = rareFile;
        await vm.runInContext('loadRare()', context);
        assert.equal(el('rareList').innerHTML.split('<li ').length - 1, palCount);
        for (const trouble of [503, 'drop', 'garbage']) {
            answer = trouble;
            await vm.runInContext('loadRare()', context);
            assert.equal(el('rareList').innerHTML.split('<li ').length - 1, palCount, `the list survives "${trouble}"`);
        }
        vm.runInContext('rareData = null', context);
        answer = 'garbage';
        await vm.runInContext('loadRare()', context);
        assert.match(el('rareSummary').textContent, /could not be read just now/);
    } finally {
        context.fetch = real;
    }

    // On the eBay prices page a game priced only for the Rarest page shows only its own site.
    vm.runInContext(`setPrices(__rarePrices, null); renderPrices(undefined, ${now}, 'en-GB')`, context);
    const sengokuPriced = el('pricesList').innerHTML.split('<li ').find(html => html.includes('Sengoku Anthology'));
    assert.match(sengokuPriced, /level-rare[^>]*>rarest</);
    assert.doesNotMatch(sengokuPriced, /ebay-flag">US/);
    vm.runInContext('setPrices(null, null); renderPrices(null)', context);

    const page = read('index.html');
    assert.match(page, /const RARE_SITE = \{ PAL: 'UK', US: 'US' \};/);
    const python = read('ebay_prices.py');
    assert.match(python, /RARE_SITES = \{"PAL": "EBAY_GB", "US": "EBAY_US"\}/, 'the page and the price job agree on which site prices which list');
});

await check('the sites the page shows are the ones the price job prices, each on its own clock', async () => {
    const python = read('ebay_prices.py');
    const block = python.slice(python.indexOf('MARKETS = {'), python.indexOf('# ---- How often each game is checked'));
    const labels = [...block.matchAll(/"label": "(\w+)"/g)].map(match => match[1]);
    assert.deepEqual(evalJson('PRICE_SITES'), ['US', 'UK', 'DE', 'FR', 'IT', 'ES']);
    assert.deepEqual([...labels].sort(), [...evalJson('PRICE_SITES')].sort(), 'MARKETS in ebay_prices.py and PRICE_SITES agree');
    assert.deepEqual(Object.keys(evalJson('PRICE_SEARCH')).sort(), [...labels].sort(), 'each site has a search link');
    for (const label of labels) {
        assert.ok(evalJson(`PRICE_LOOKUPS.some(lookup => lookup.id === PRICE_SEARCH.${label})`), `${label}: its link exists`);
    }
    assert.equal(evalJson("currencyOf('DE', null)"), 'EUR');
    assert.equal(evalJson("currencyOf('FR', null)"), 'EUR');
    assert.equal(evalJson("currencyOf('IT', null)"), 'EUR');
    assert.equal(evalJson("currencyOf('ES', null)"), 'EUR');
    for (const label of ['DE', 'FR', 'IT', 'ES']) {
        const clock = block.match(new RegExp(`"label": "${label}"[\\s\\S]*?"min_every_hours": (\\d+)`));
        assert.ok(clock && evalJson(`SITE_STALE_HOURS.${label}`) > Number(clock[1]), `${label}: dimmed only after its whole check interval`);
    }
    assert.equal(evalJson("currencyOf('UK', null)"), 'GBP');
    assert.equal(evalJson("currencyOf('US', null)"), 'USD');
    // A site with a slower clock (min_every_hours) is overdue later than its game's level says.
    const slower = block.match(/"label": "DE"[\s\S]*?"min_every_hours": (\d+)/);
    assert.ok(slower, 'Germany has its own clock in the price job');
    assert.ok(evalJson("SITE_STALE_HOURS.DE") > Number(slower[1]), 'overdue only after a whole check interval and a bit more');
    assert.equal(evalJson("staleFor({}, 8, 'DE')"), evalJson('SITE_STALE_HOURS.DE'));
    assert.equal(evalJson("staleFor({}, 8, 'UK')"), 8, 'the UK is as before');
    assert.equal(evalJson("staleFor({ steady: true }, 8, 'DE')"), 56);
    // A German figure is shown in euros, beside its flag, and is not dimmed after nine hours.
    const html = evalJson(`priceSiteHtml('DE', { checked: '2026-10-06T03:00Z', copies: 12, lowest: 8, median: 14.5, postage: 3 }, 'EUR', ${Date.parse('2026-10-06T12:00:00Z')}, 'en-GB', staleFor({}, 8, 'DE'))`);
    assert.match(html, /<span class="ebay-flag">DE<\/span>/);
    assert.match(html, /€14\.50/);
    assert.doesNotMatch(html, /is-stale/);
});

await check('the Rarest page: a note shows its own release-fact links, and only https ones', async () => {
    const rareFile = JSON.parse(read('rare_games.json'));
    const base = rareFile.lists.PAL[0];
    context.__rare = { ...rareFile, lists: { ...rareFile.lists, PAL: [
        { ...base, note: 'Out in Europe first.', note_sources: ['https://en.wikipedia.org/wiki/Kuon', 'javascript:alert(1)'] },
        { ...base, title: 'Plain', note: 'Only a note.', note_sources: undefined },
    ] } };
    vm.runInContext(`setPrices(null, null); rareRegion = 'PAL'; renderRare(__rare, ${Date.parse('2026-10-16T12:00:00Z')}, 'en-GB')`, context);
    const rows = el('rareList').innerHTML.split('<li ').slice(1);
    assert.match(rows[0], /Out in Europe first\. [^]*Release facts: <a href="https:\/\/en\.wikipedia\.org\/wiki\/Kuon"[^>]*>en\.wikipedia\.org<\/a>/);
    assert.ok(!rows[0].includes('javascript:'), 'a link that is not https is not drawn');
    assert.ok(!rows[1].includes('Release facts'), 'no sources, no line');
});

await check('the Rarest page: the rarest consoles, priced on both sites', async () => {
    const consoles = JSON.parse(read('rare_consoles.json'));
    const now = Date.parse('2026-10-08T12:00:00Z');
    const site = (median, copies = 2) => ({ checked: '2026-10-08T09:00Z', copies, lowest: median - 10, median });
    const red = consoles.consoles.find(row => row.name.includes('Super Red'));
    const pink = consoles.consoles.find(row => Array.isArray(row.sites) && row.sites.length === 1 && row.price !== false);
    const prices = { currencies: { US: 'USD', UK: 'GBP' }, games: {
        [red.name]: { level: 'rare', mentions: 0, kind: 'console', sites: ['US', 'UK'], US: site(3500), UK: site(2800) },
        [pink.name]: { level: 'rare', mentions: 0, kind: 'console', sites: pink.sites, [pink.sites[0]]: site(80) },
        Kuon: { level: 'normal', mentions: 1, UK: site(300), US: site(900) },
    } };
    context.__consoles = consoles;
    context.__consolePrices = prices;
    vm.runInContext(`setPrices(__consolePrices, null); consoleData = __consoles; showRareRegion('Consoles')`, context);
    vm.runInContext(`renderRare(rareData, ${now}, 'en-GB')`, context);
    assert.equal(el('rareHeading').textContent, 'Rarest PS2 Consoles');
    assert.equal(evalJson("document.getElementById('rareRegionConsoles').getAttribute('aria-pressed')"), 'true');
    assert.equal(evalJson("document.getElementById('rareRegionPAL').getAttribute('aria-pressed')"), 'false');
    const draw = (region) => {
        vm.runInContext(`showConsoleRegion(${JSON.stringify(region)}); renderRare(rareData, ${now}, 'en-GB')`, context);
        return el('rareList').innerHTML.split('<li ').slice(1);
    };
    const inRegion = (codes) => consoles.consoles.filter(row => row.regions.some(code => codes.includes(code)));
    const guideOrder = (rows) => rows.map(row => row.value?.usd ?? -1);

    // Japan opens first; each region holds the consoles sold there, most expensive first.
    let rows = draw('JP');
    assert.equal(evalJson("document.getElementById('consoleRegionJP').getAttribute('aria-pressed')"), 'true');
    assert.equal(el('consoleRegions').classList.contains('hidden'), false);
    assert.equal(rows.length, inRegion(['JP']).length);
    assert.match(rows[0], new RegExp(`#1 ${esc(red.name).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`), 'the dearest eBay US median first');
    assert.match(rows[0], /<span class="ebay-flag">US<\/span><b class="ebay-median">\$3,500<\/b>/);
    assert.match(rows[0], /<span class="ebay-flag">UK<\/span><b class="ebay-median">£2,800<\/b>/);
    assert.match(rows[0], /<span class="rarity-badge rarity-1" title="5,000 or fewer made, or a one-off\.">Ultra rare<\/span>/, 'how rare, in words');
    assert.doesNotMatch(rows[0], /tier \d/);
    assert.deepEqual([...el('rareNote').innerHTML.matchAll(/rarity-badge rarity-(\d)">([^<]+)</g)].map(m => `${m[1]} ${m[2]}`),
        ['1 Ultra rare', '2 Very rare', '3 Rare', '4 Limited'], 'a one-line key to the four words');
    assert.match(rows[0], /SCPH-30000 and 2 more models · Japan, US, Europe, UK · 2001 · about 1,998 made/, 'one short line; every model in its hint');
    assert.match(rows[0], /guide \$4,000/);
    assert.match(rows[1], /#2 /);
    // The rest have no eBay figure yet: by their guide value, dearest first, those without one last.
    const unpriced = inRegion(['JP']).filter(row => row !== red).sort((a, b) => (b.value?.usd ?? -1) - (a.value?.usd ?? -1) || a.rank - b.rank);
    rows.slice(1).forEach((html, i) => assert.ok(html.includes(esc(unpriced[i].name)), `${i + 2}: ${unpriced[i].name}`));
    assert.deepEqual(guideOrder(unpriced), [...guideOrder(unpriced)].sort((a, b) => b - a));
    const prototype = rows.find(html => html.includes('not priced'));
    assert.match(prototype, /never sold/, 'the one-off display unit is never looked up');
    assert.equal(rows.filter(html => html.includes('list-extra')).length, Math.max(rows.length - 25, 0));
    assert.match(el('rareSummary').textContent, /^\d+ official consoles sold in Japan, most expensive first by eBay US price; those with none for sale follow, by guide value · 2 prices with copies for sale$/);

    rows = draw('PAL');
    assert.equal(rows.length, inRegion(['EU', 'UK']).length);
    assert.ok(rows[0].includes(esc(red.name)), 'PAL goes by eBay UK: £2,800 first');
    assert.ok(rows[1].includes(esc(pink.name)), 'then £80');
    assert.equal((rows[1].match(/ebay-flag/g) || []).length, 1, 'a console sold in one region is priced on its site only');
    assert.match(el('rareSummary').textContent, /sold in PAL, most expensive first by eBay UK price/);
    rows = draw('US');
    assert.equal(rows.length, inRegion(['US', 'CA']).length);
    assert.ok(!rows.some(html => html.includes(esc(pink.name))), 'a European console is not in the US list');
    vm.runInContext("showConsoleRegion('constructor')", context);
    assert.equal(evalJson('consoleRegion'), 'JP');
    vm.runInContext("showRareRegion('PAL')", context);
    assert.equal(el('consoleRegions').classList.contains('hidden'), true, 'the console regions show with the consoles only');
    vm.runInContext("showRareRegion('Consoles')", context);
    assert.match(read('retro.css'), /body \.console-regions:not\(\.hidden\) \{ display: flex;/, 'a display rule must not overrule "hidden"');
    assert.ok(consoles.consoles.every(row => Array.isArray(row.regions) && row.regions.some(code => ['US', 'CA', 'JP', 'EU', 'UK'].includes(code))),
        'every console is in at least one region list');
    const page = read('index.html');
    assert.match(page, />PAL<\/button>\s*<button[^>]*>US<\/button>\s*<button[^>]*>Consoles<\/button>/, 'the buttons say PAL and US, nothing more');

    // The eBay prices page is for games: consoles stay on the Rarest page.
    vm.runInContext(`renderPrices(undefined, ${now}, 'en-GB')`, context);
    assert.doesNotMatch(el('pricesList').innerHTML, /Super Red/);
    assert.match(el('pricesList').innerHTML, /Kuon/);
    assert.equal(evalJson(`compactPriceHtml(${JSON.stringify(red.name)})`), '', 'nor do they show beside names in the feed');

    // A hostile file is text, never markup.
    context.__hostile = { tiers: { 1: '<b>' }, consoles: [{ name: '<img src=x onerror=alert(1)>', tier: '1: x', rank: 1, models: ['<i>'], regions: ['JP', '<b>'],
        why_rare: '<script>', not_retail: true, price: false, not_priced_because: '"><b>', evidence: [{ source: 'javascript:alert(1)' }],
        value: { usd: '9', what: '<b>' } }] };
    vm.runInContext(`renderRareConsoles(__hostile, ${now}, 'en-GB')`, context);
    assert.match(el('rareList').innerHTML, /&lt;img src=x/, 'drawn, as text');
    const hostile = el('rareList').innerHTML;
    assert.doesNotMatch(hostile, /<img|<script|<i>|<b>|javascript:/);
    assert.doesNotMatch(hostile, /guide/);
    vm.runInContext("consoleData = null; consoleTrouble = false; renderRare()", context);
    assert.equal(el('rareSummary').textContent, 'No list of rare consoles yet.');
    vm.runInContext("showRareRegion('PAL'); setPrices(null, null)", context);
    assert.equal(el('rareHeading').textContent, 'Rarest PS2 Games');
});

await check('the PS2 price index: the latest value, its moves and a line of every day', async () => {
    const index = { sites: {
        UK: [['2026-10-06', 100, 145], ['2026-10-07', 99.87, 135], ['2026-10-08', 101.2, 167], ['2026-10-13', 104.5, 170], ['2026-10-14', 103.9, 160]],
        US: [['2026-10-06', 100, 162]],
        EU: [['2026-10-06', 100, 1]],
    } };
    context.__index = index;
    vm.runInContext("renderIndex(__index, 'en-GB')", context);
    assert.equal(el('indexSection').classList.contains('hidden'), false);
    assert.equal(el('indexSummary').textContent, "100 = 6 Oct. How used PS2 games' asking prices have moved since, per site, up to the last full day (UTC).");
    const [us, uk] = el('indexCards').innerHTML.split('class="index-card"').slice(1);
    const cards = [uk, us];
    assert.equal(el('indexCards').innerHTML.split('class="index-card"').length, 3, 'the two sites, never a third');
    assert.match(cards[0], /eBay UK · 14 Oct/);
    assert.match(cards[0], /<div class="index-value">103\.9<\/div>/);
    assert.match(cards[0], /is-down">▼ 0\.6% since 13 Oct</, '103.9 against 104.5');
    assert.match(cards[0], /is-up">▲ 4\.0% since 7 Oct</, 'a week: against 7 Oct, the last day a week or more before (99.87)');
    assert.match(cards[0], /<polyline points="0\.0,[\d.]+ 60\.0,/);
    assert.match(cards[0], /160 games compared with their previous day/);
    assert.match(cards[1], /<div class="index-value">100\.0<\/div>/);
    assert.doesNotMatch(cards[1], /index-line|ebay-change/, 'one day: nothing to compare and no line');
    assert.match(cards[1], /162 games priced on its first day/);
    assert.equal(evalJson("indexChange([['2026-10-07', 100, 1], ['2026-10-08', 100.04, 1]], 1)").change.toFixed(2), '0.04');
    assert.match(evalJson("indexChangeHtml({ change: 0.04, day: '2026-10-07' }, (day) => day)"), /no change since 2026-10-07/);
    // The PAL card (every PAL site together) comes after the US and before the single sites.
    context.__pal = { sites: { UK: [['2026-10-06', 100, 100], ['2026-10-07', 101, 100]], DE: [['2026-10-06', 100, 100], ['2026-10-07', 102, 100]],
        PAL: [['2026-10-06', 100, 200], ['2026-10-07', 101.5, 200]], US: [['2026-10-06', 100, 100], ['2026-10-07', 99, 100]] } };
    vm.runInContext("renderIndex(__pal, 'en-GB')", context);
    const palCards = el('indexCards').innerHTML.split('class="index-card"').slice(1);
    assert.equal(palCards.length, 4);
    assert.deepEqual(palCards.map(card => card.match(/ebay-flag">(\w+)</)[1]), ['US', 'PAL', 'UK', 'DE']);
    assert.match(palCards[1], /all PAL sites · 7 Oct/);
    assert.match(palCards[1], /<div class="index-value">101\.5<\/div>/);
    assert.match(el('indexSummary').textContent, /"All PAL sites" counts every game on the UK and the euro sites together\./);
    assert.match(palCards[2], /eBay UK · 7 Oct/);
    // A day with too few games kept its value: it says so, and does not claim "no change".
    context.__kept = { min_games: 10, sites: { UK: [['2026-10-06', 100, 145], ['2026-10-07', 101, 140], ['2026-10-08', 101, 4]] } };
    vm.runInContext("renderIndex(__kept, 'en-GB')", context);
    assert.match(el('indexCards').innerHTML, /Only 4 games could be compared that day, too few to move it/);
    assert.doesNotMatch(el('indexCards').innerHTML, /since 7 Oct/);

    // A broken or hostile file shows nothing rather than nonsense.
    for (const bad of [null, {}, { sites: [] }, { sites: { UK: 'x' } }, { sites: { UK: [['soon', 100, 1], ['2026-10-07', -5, 1], ['2026-10-08', 'x', 1]] } }]) {
        context.__bad = bad;
        vm.runInContext("renderIndex(__bad, 'en-GB')", context);
        assert.equal(el('indexSection').classList.contains('hidden'), true, JSON.stringify(bad));
    }
    context.__hostile = { sites: { UK: [['2026-10-06', 100, '<b>'], ['2026-10-07', 101, '<img src=x>']] } };
    vm.runInContext("renderIndex(__hostile, 'en-GB')", context);
    assert.doesNotMatch(el('indexCards').innerHTML, /<b>|<img/);

    // Loaded with the prices; a hiccup keeps what is on screen.
    const real = context.fetch;
    let answer = index;
    context.fetch = async (path) => {
        if (path !== 'data/prices/index.json') return { ok: false, status: 404, json: async () => ({}) };
        if (answer === 'drop') throw new TypeError('Failed to fetch');
        return { ok: true, status: 200, json: async () => answer };
    };
    try {
        await vm.runInContext('loadPrices()', context);
        assert.equal(el('indexSection').classList.contains('hidden'), false);
        answer = 'drop';
        await vm.runInContext('loadPrices()', context);
        assert.equal(el('indexSection').classList.contains('hidden'), false, 'a hiccup keeps the index');
    } finally {
        context.fetch = real;
    }
    vm.runInContext('indexData = null; renderIndex()', context);
    assert.equal(el('indexSection').classList.contains('hidden'), true);
    const page = read('index.html');
    assert.ok(page.indexOf('id="indexSection"') > page.indexOf('id="viewPrices"') && page.indexOf('id="indexSection"') < page.indexOf('id="pricesSection"'),
        'at the top of the eBay prices page');
});

await check('Digital-Only News: the flagged items, counted over two weeks and the last seven days', () => {
    const at = (days) => new Date(Date.now() - days * 86400000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
    context.__feed = [
        { headline: 'Phantom Blade Zero Confirmed Digital-Only Despite Promised Physical Release - Power Up Gaming', source: 'r/playstation',
          link: 'https://r.example/pbz', matched_game: null, is_digital_only: true, sentiment: 50, timestamp: at(1) },
        { headline: 'Sony <b>to ditch discs</b>', source: 'Kotaku', link: 'https://k.example/discs', matched_game: null,
          is_digital_only: true, sentiment: 50, timestamp: at(10) },
        { headline: 'Rise Of The Tomb Raider Physical Release Announced', source: 'Nintendo Life', link: 'https://n.example/lrg',
          matched_game: null, is_digital_only: false, sentiment: 50, timestamp: at(2) },
        { headline: 'Older item saved before the flag', source: 'Kotaku', link: 'https://k.example/old', matched_game: null, sentiment: 50, timestamp: at(3) },
    ];
    vm.runInContext('allFeedData = __feed; refreshDashboard()', context);
    el('filterSelect').value = 'digital';
    el('searchInput').value = '';
    el('typeSelect').value = 'all';
    vm.runInContext('filterFeedItems()', context);
    assert.equal(el('feedSummary').textContent,
        '2 of 4 items are about digital-only games and discs going away, 1 of them in the last 7 days. Any game, not only PS2.');
    const rows = el('feedTableBody').children.map(row => row.innerHTML);
    assert.equal(rows.length, 2);
    assert.match(rows[0], /<span class="digital-tag[^"]*"[^>]*>Digital-only<\/span>/);
    assert.match(rows[1], /Sony &lt;b&gt;to ditch discs&lt;\/b&gt;/, 'a headline is text, never markup');
    context.__kept = { total_stories: 41, days: { '2026-10-08': 12, '2026-09-27': 1, 'bad': 3 } };
    vm.runInContext('digitalArchive = __kept; filterFeedItems()', context);
    assert.match(el('feedSummary').textContent, /Any game, not only PS2\. 41 archived since 27 Sept? \(the archive is updated every 6 hours\)\.$/, 'the archive counts beyond two weeks');
    vm.runInContext('digitalArchive = null', context);
    el('searchInput').value = 'phantom';
    vm.runInContext('filterFeedItems()', context);
    assert.equal(el('feedSummary').textContent, 'Listing 1 of the 2 items about digital-only games and discs going away.');
    el('filterSelect').value = 'all';
    el('searchInput').value = '';
    vm.runInContext('filterFeedItems()', context);
    assert.equal((el('feedTableBody').children.map(row => row.innerHTML).join('').match(/digital-tag/g) || []).length, 2,
        'the tag shows in every view');
    vm.runInContext('allFeedData = []; refreshDashboard()', context);
});

await check('the Rarest charts: index and market cap per list, a game\'s history, and a plain line without the library', async () => {
    const index = { rare: { survival: 0.65, lists: {
        PAL: { site: 'UK', currency: 'GBP', games: 110, points: [
            ['2026-10-08', 100, 90, 230000000, 148000000, 90], ['2026-10-09', 99.84, 79, 280000000, 162000000, 96],
            ['2026-10-12', 103.5, 85, 286000000, 171000000, 96], ['bad', 1, 1, 1, 1, 1], ['2026-10-13', 0, 1, 1, 1, 1]] },
        US: { site: 'US', currency: 'USD', games: 105, points: [] },
    } } };
    context.__rareIndex = index;
    vm.runInContext("rareChart.measure = 'index'; rareChart.range = 'All'; renderRareChart('PAL', __rareIndex, 'en-GB')", context);
    assert.equal(el('rareChart').classList.contains('hidden'), false);
    const stats = el('rareChartStats').innerHTML;
    assert.match(stats, /PAL rare index<\/span><b>103\.50<\/b> <span class="ebay-change is-up">▲ 3\.5%<\/span>/);
    assert.match(stats, /Market cap<\/span><b>£286[Mm]<\/b> <span class="ebay-change is-up">▲ 24\.3%<\/span>/);
    assert.match(stats, /Without big sellers<\/span><b>£171[Mm]<\/b>/);
    assert.match(el('rareChartLegend').innerHTML, /12 Oct 2026 · <b>103\.50<\/b> · 85 games compared with their day before$/);
    // Without the library, a plain line of the three good days, its range written beside it.
    const plain = el('rareChartCanvas').innerHTML;
    assert.match(plain, /<polyline points="0\.0,203\.3 300\.0,212\.0 600\.0,12\.0"/);
    assert.match(plain, /chart-plain-high">103\.50<.*chart-plain-low">99\.84</s);
    assert.match(el('rareChartNote').innerHTML, /^100 = 8 Oct 2026\. How the asking prices of this list moved on eBay UK/);
    const tools = el('rareChartTools').innerHTML;
    for (const label of ['Index', 'Market cap', '1W', '1M', '3M', 'All', 'Line', 'Area', 'Log']) assert.match(tools, new RegExp(`>${label}</button>`), label);
    assert.doesNotMatch(tools, /Without big sellers/, 'the market cap\'s choice of games only with the market cap');
    assert.match(tools, /class="chart-tool is-active" aria-pressed="true"[^>]*onclick="setChart\('rare', 'measure', 'index'\)">Index</);

    vm.runInContext("indexData = __rareIndex; rareRegion = 'PAL'; setChart('rare', 'measure', 'cap')", context);
    assert.match(el('rareChartLegend').innerHTML, /<b>£286[Mm]<\/b> · 96 of 110 games priced$/);
    assert.match(el('rareChartTools').innerHTML, /onclick="setChart\('rare', 'scope', 'core'\)">Without big sellers</);
    assert.match(el('rareChartNote').innerHTML, /Market cap = each game's eBay UK median × the copies thought to have been sold in PAL countries × 65% still around\. .*Kuon: about 12,000 US, 8,000 PAL/);
    vm.runInContext("setChart('rare', 'scope', 'core')", context);
    assert.match(el('rareChartLegend').innerHTML, /<b>£171[Mm]<\/b>/);
    vm.runInContext("setChart('rare', 'range', '1W')", context);
    assert.equal(/points="([^"]*)"/.exec(el('rareChartCanvas').innerHTML)[1].split(' ').length, 3, 'the 8th is within a week of the 12th');
    context.__days = ['2026-09-01', '2026-09-20', '2026-10-05', '2026-10-06', '2026-10-13'].map(time => ({ time, value: 1 }));
    assert.deepEqual(evalJson("inRange(__days, '1W').map(p => p.time)"), ['2026-10-06', '2026-10-13']);
    assert.deepEqual(evalJson("inRange(__days, '1M').map(p => p.time)"), ['2026-09-20', '2026-10-05', '2026-10-06', '2026-10-13']);
    assert.equal(evalJson("inRange(__days, 'All').length"), 5);
    vm.runInContext("setChart('rare', 'log', null)", context);
    assert.equal(evalJson('rareChart.log'), true, 'a switch turns on and off');
    vm.runInContext("setChart('rare', 'constructor', 'x')", context);
    assert.equal(evalJson('rareChart.constructor === Object'), true, 'only its own settings');
    vm.runInContext("Object.assign(rareChart, { measure: 'index', scope: 'all', range: 'All', log: false })", context);

    // No points (the US list today, the consoles, an old index.json): no chart at all.
    for (const [region, data] of [['US', index], ['Consoles', index], ['PAL', {}], ['PAL', null], ['PAL', { rare: { lists: { PAL: { points: 'x' } } } }]]) {
        context.__data = data;
        vm.runInContext(`renderRareChart(${JSON.stringify(region)}, __data, 'en-GB')`, context);
        assert.equal(el('rareChart').classList.contains('hidden'), true, `${region} ${JSON.stringify(data)}`);
    }

    // A game's chart: from series.json, per site, with the copies under each day.
    const series = { start: '2026-10-06', games: { Kuon: { US: [[0, 1100, 2], [2, 950, 4], ['x', 1, 1], [3, -1, 1]], UK: [[1, 800, 1]] } } };
    context.__series = series;
    assert.deepEqual(evalJson("gamePoints(__series, 'Kuon', 'US')"), [
        { time: '2026-10-06', value: 1100, copies: 2 }, { time: '2026-10-08', value: 950, copies: 4 }]);
    assert.deepEqual(evalJson("gamePoints(__series, 'constructor', 'US')"), []);
    assert.deepEqual(evalJson("gamePoints({ games: __series.games }, 'Kuon', 'US')"), [], 'no start, no days');
    const button = evalJson("chartButtonHtml('Kuon', 'US')");
    assert.equal(button, evalJson("chartButtonHtml('Kuon', 'US')"), 'one button number per game and site');
    const n = Number(/openGameChart\((\d+)\)/.exec(button)[1]);
    assert.match(evalJson(`chartButtonHtml('<b>"', 'UK')`), /title="Price history of &lt;b&gt;&quot;"/);
    vm.runInContext(`seriesData = __series; openGameChart(${n})`, context);
    await new Promise(done => setTimeout(done, 0));
    assert.equal(el('gameChart').classList.contains('hidden'), false);
    assert.equal(el('gameChartTitle').textContent, 'Kuon');
    assert.match(el('gameChartLegend').innerHTML, /^eBay US · (?:8 Oct|Oct 8,) 2026 · median <b>\$950<\/b> · 4 copies for sale$/);
    assert.match(el('gameChartTools').innerHTML, />eBay US<\/button>.*>eBay UK<\/button>/s, 'both sites have figures: both offered');
    vm.runInContext("setChart('game', 'site', 'UK')", context);
    assert.match(el('gameChartLegend').innerHTML, /^eBay UK · (?:7 Oct|Oct 7,) 2026 · median <b>£800<\/b> · 1 copy for sale$/);
    assert.match(el('gameChartCanvas').innerHTML, /One day so far/);
    vm.runInContext('closeGameChart()', context);
    assert.equal(el('gameChart').classList.contains('hidden'), true);
    // A game with no history yet, and a history file that cannot be read.
    const other = Number(/openGameChart\((\d+)\)/.exec(evalJson("chartButtonHtml('Okami', 'UK')"))[1]);
    vm.runInContext(`openGameChart(${other})`, context);
    await new Promise(done => setTimeout(done, 0));
    assert.match(el('gameChartNote').textContent, /^No figures on eBay UK yet/);
    vm.runInContext(`seriesData = null; openGameChart(${other})`, context);
    for (let i = 0; i < 5; i++) await new Promise(done => setTimeout(done, 0));
    assert.match(el('gameChartNote').textContent, /could not be read just now/, 'series.json is a 404 here');
    vm.runInContext('closeGameChart(); openGameChart(9999)', context);
    assert.equal(el('gameChart').classList.contains('hidden'), true, 'an unknown button opens nothing');

    // The game's page offers the chart (the lists keep only the short prices).
    const page = read('index.html');
    assert.match(page, /\$\{prices\s*\? ` \$\{chartButtonHtml\(prices\.title, label\)\}` : ''\}/);
    assert.match(page, /chartButtonHtml\(row\.title, sites\.includes\('UK'\) \? 'UK' : sites\[0\]\)/);
    assert.match(page, /lightweight-charts@\d+\.\d+\.\d+\/dist\/lightweight-charts\.standalone\.production\.js/, 'a fixed version');
    assert.equal((page.match(/Charts by <a href="https:\/\/www\.tradingview\.com\/"/g) || []).length, 2, 'the library\'s credit under both charts');
});

await check('charts on a phone: a finger drag scrolls the page, a tap reads a day, the tools are one row you swipe', () => {
    const page = read('index.html');
    assert.match(page, /handleScroll: \{ horzTouchDrag: false, vertTouchDrag: false \}/, 'touch drags are left to the page');
    assert.match(page, /chart\.subscribeClick\(param => \{ if \(param\?\.point\) spec\.onHover\?\.\(dayAt\(param\)\); \}\);/, 'a tap reads a day');
    const css = read('retro.css').replace(/\/\*[\s\S]*?\*\//g, '');
    const phone = /@media \(max-width: 640px\) \{\s*body \.chart-canvas[\s\S]*?\n\}/.exec(css)?.[0] || '';
    assert.match(phone, /body \.chart-tools \{[^}]*flex-wrap: nowrap;[^}]*overflow-x: auto/);
    assert.match(phone, /body main \.chart-tools \.chart-tool \{[^}]*min-height: 2\.25rem/, 'smaller than the general 44px button rule, which it must out-rank');
});

await check('the EUR button: converts at the ECB rate, marks it, keeps PriceCharting guides in dollars, hides without rates', () => {
    const run = (code) => vm.runInContext(code, context);
    // No rates, no button, and prices are exactly as before.
    run('setFx(null)');
    assert.equal(el('currencyRow').classList.contains('hidden'), false, 'not painted until the rates were read');
    run('paintCurrency()');
    assert.equal(el('currencyRow').classList.contains('hidden'), true);
    assert.equal(evalJson("money(100, 'USD', 'en-GB')"), '$100');
    // A rate that is not a positive number is dropped; a file with none is no file.
    run("setFx({ date: '2026-10-13', rates: { USD: -1, GBP: 'x', EUR: 1 } })");
    assert.equal(evalJson('fxData'), null);
    run("setFx({ date: '2026-10-13', rates: { USD: 1.25, GBP: 0.8, XXX: 0, EUR: 1 } })");
    assert.deepEqual(evalJson('fxData'), { date: '2026-10-13', rates: { USD: 1.25, GBP: 0.8 } });
    run('paintCurrency()');
    assert.equal(el('currencyRow').classList.contains('hidden'), false, 'shown once there are rates');
    assert.equal(evalJson("money(5, 'USD', 'en-GB')"), '$5.00', 'off by default');
    // On: other currencies are divided by the rate and marked; euros and guides are not.
    run('setCurrency(true, false)');
    assert.equal(evalJson('showEuro'), true);
    assert.equal(el('currencyToggle').getAttribute('aria-pressed'), 'true');
    assert.match(el('currencyNote').textContent, /^≈ converted at the European Central Bank rate of 13 Oct 2026$/);
    assert.equal(evalJson("money(5, 'USD', 'en-GB')"), '≈€4.00');
    assert.equal(evalJson("money(80, 'GBP', 'en-GB')"), '≈€100');
    assert.equal(evalJson("money(10, 'EUR', 'en-GB')"), '€10.00', 'a price already in euros is not marked');
    assert.equal(evalJson("money(100, 'USD', 'en-GB', false)"), '$100', 'the PriceCharting guide stays in dollars');
    assert.equal(evalJson("money(null, 'USD', 'en-GB')"), '');
    assert.match(evalJson("money(5, 'CHF', 'en-GB')"), /^CHF\s5\.00$/, 'a currency with no rate is shown as it is');
    assert.match(evalJson("moneyShort(286000000, 'GBP', 'en-GB')"), /^≈€357\.5[Mm]$/);
    assert.equal(evalJson("inEuros(5, 'USD', false).mark"), '');
    // The week's change (an amount and a percentage) converts the amount only.
    assert.match(evalJson("priceChangeHtml({ median: 12, week: { median: 10, checked: '2026-10-06T12:00Z' } }, 'USD', 'en-GB')"), /\(≈€1\.60 ▲ 20%\)/);
    // Off again, and a file that stops giving rates switches it off by itself.
    run('setCurrency(false, false)');
    assert.equal(evalJson("money(5, 'USD', 'en-GB')"), '$5.00');
    run('setCurrency(true, false); setFx(null)');
    assert.equal(evalJson('showEuro'), false);
    run('paintCurrency()');
    // The page reads the rates before the prices, so the first list drawn is already right.
    const page = read('index.html');
    assert.ok(page.indexOf('await loadFx();') < page.indexOf('await loadPrices();'));
    assert.match(page, /fetch\('data\/fx\.json', \{ cache: 'no-cache' \}\)/);
});

await check('search suggests from the whole library and opens a game page; the logo goes home; the 24-hour list sorts by rarity', async () => {
    const run = (code) => vm.runInContext(code, context);
    run(`setLibrary(['God Hand', 'Godzilla: Save the Earth', 'Kuon', 'Kingdom Hearts II', 'CY Girls', 'Final Fantasy X', 'Final Fantasy XII', 'Dragon Quest VIII: Journey of the Cursed King'])`);
    assert.equal(evalJson(`suggestGames('godh')[0]`), 'God Hand', '"godh" finds God Hand');
    assert.equal(evalJson(`suggestGames('GOD H')[0]`), 'God Hand', 'spaces and capitals do not matter');
    assert.deepEqual(evalJson(`suggestGames('god')`), ['God Hand', 'Godzilla: Save the Earth']);
    // One entry per game, whichever spelling the library has: the colon one is shown, all find it.
    run(`setLibrary(['Medal of Honor Frontline', 'Medal of Honor: Frontline', 'Medal of Honor - Frontline', 'Medal of Honor: European Assault',
        'Goblin Commander: Unleash The Horde', 'Goblin Commander: Unleash the Horde', 'Getaway, The', 'The Getaway', 'FIFA Soccer 10', 'FIFA 11', 'FIFA 10', 'God Hand', 'Kuon'])`);
    assert.deepEqual(evalJson(`suggestGames('medal of honor frontline')`), ['Medal of Honor: Frontline']);
    assert.deepEqual(evalJson(`suggestGames('medal of honour frontline')`), ['Medal of Honor: Frontline'], 'British spelling');
    assert.deepEqual(evalJson(`suggestGames('goblin commander')`).length, 1);
    assert.equal(evalJson(`suggestGames('getaway').length`), 1, 'The Getaway and Getaway, The are one game');
    assert.deepEqual(evalJson(`suggestGames('fifa 10')`).sort(), ['FIFA 10', 'FIFA Soccer 10'], 'words in any form, in the name or not');
    assert.deepEqual(evalJson(`suggestGames('fifa 11')`), ['FIFA 11']);
    run(`setLibrary(['God Hand', 'Godzilla: Save the Earth', 'Kuon', 'Kingdom Hearts II', 'CY Girls', 'Final Fantasy X', 'Final Fantasy XII', 'Dragon Quest VIII: Journey of the Cursed King'])`);
    assert.equal(evalJson(`suggestGames('cursed')[0]`), 'Dragon Quest VIII: Journey of the Cursed King', 'any word, any part');
    assert.deepEqual(evalJson(`suggestGames('')`), []);
    assert.deepEqual(evalJson(`suggestGames('zzzz')`), []);
    assert.equal(evalJson(`suggestGames('final fantasy x')[0]`), 'Final Fantasy X', 'the shortest match leads');
    assert.equal(evalJson(`suggestGames('god', 1).length`), 1);
    // Typing fills the list; a click on one opens its page and puts the address on it.
    el('gameSearch').value = 'godh';
    run('onGameSearchInput()');
    assert.equal(el('gameSuggest').classList.contains('hidden'), false);
    assert.match(el('gameSuggest').innerHTML, /God Hand/);
    // Items for the page: spelled another way, still the same game; a switched-off source stays out.
    run(`visibleFeedData = [
        { headline: 'Old <b>news</b>', source: 'r/ps2', timestamp: '2026-10-10 10:00:00 UTC', link: 'https://example.com/a', matched_games: ['God Hand'], feed: 'reddit:ps2' },
        { headline: 'New thread', source: '/vr/', feed: '4chan:vr', timestamp: '2026-10-12 10:00:00 UTC', link: 'javascript:alert(1)', matched_game: 'God Hand' },
        { headline: 'Other', source: 'x', timestamp: '2026-10-12 10:00:00 UTC', link: 'https://example.com/c', matched_games: ['Kuon'] },
    ]`);
    addressChanges.length = 0;
    assert.equal(run(`openGame('God Hand')`), 'game');
    assert.deepEqual(addressChanges, ['#game=God%20Hand']);
    assert.equal(el('viewGame').classList.contains('hidden'), false);
    for (const panel of ['viewDashboard', 'viewRare', 'viewMentions', 'viewPrices']) assert.equal(el(panel).classList.contains('hidden'), true, `${panel} is away`);
    assert.equal(el('gameTitle').textContent, 'God Hand');
    const rows = el('gameItems').innerHTML.split('<li ').slice(1);
    assert.equal(rows.length, 2);
    assert.match(rows[0], /New thread/, 'newest first');
    assert.doesNotMatch(el('gameItems').innerHTML, /<b>news|javascript:/, 'nothing from a feed is markup or a script link');
    assert.match(el('gameItems').innerHTML, /Old &lt;b&gt;news&lt;\/b&gt;/);
    // A game nobody has named: an empty page that says so, no error.
    assert.equal(run(`openGame('CY Girls')`), 'game');
    assert.equal(el('gameItems').innerHTML.split('<li ').length - 1, 1);
    assert.match(el('gameItems').innerHTML, /Nothing yet/);
    assert.match(el('gameSummary').textContent, /In the PS2 library, but nothing in our feeds/);
    // Arriving by address, and Back/Forward, go through the same door.
    context.location.hash = '#game=Kuon';
    assert.equal(run('showViewFromAddress()'), 'game');
    assert.equal(el('gameTitle').textContent, 'Kuon');
    assert.match(el('gameItems').innerHTML, /Other/);
    context.location.hash = '#game=%E0%A4%A';   // a broken escape does not stop the page
    run('showViewFromAddress()');
    // The logo: home, and a clean slate.
    let prevented = 0;
    assert.equal(run(`goHome({ preventDefault() { __p(); } })`.replace('__p()', 'globalThis.__prevented = 1')), false);
    assert.equal(el('gameSearch').value, '');
    assert.equal(el('viewGame').classList.contains('hidden'), true);
    assert.equal(el('viewDashboard').classList.contains('hidden'), false);
    const page = read('index.html');
    assert.match(page, /<a class="brand-id" id="brandHome" href="\.\/" onclick="return goHome\(event\)"/, 'the logo is a link home');
    assert.match(page, /<input type="search" id="gameSearch"/);

    // A game filed under two names (ebay_prices.py prices it once) shows the same figures under both.
    run(`setPrices({ games: {
        'Ratchet: Deadlocked': { level: 'normal', mentions: 1, US: { copies: 190, median: 13.99, checked: '2026-10-14T10:00Z' }, UK: { copies: 45, median: 13.66, checked: '2026-10-14T10:00Z' } },
        'Ratchet: Gladiator': { level: 'normal', mentions: 0, US: { copies: 0, checked: '2026-10-14T10:00Z' } },
        'Sly 3': { level: 'normal', mentions: 1, UK: { copies: 5, median: 9, checked: '2026-10-14T10:00Z' } },
    } }, { regional_names: { UK: [{ from: 'Ratchet: Deadlocked', to: 'Ratchet: Gladiator' }, { from: 'Sly 3: Honor Among Thieves', to: 'Sly 3' }, { from: 7 }] } })`);
    assert.equal(evalJson(`medianOf('Ratchet: Gladiator', 'UK')`), 13.66, 'the PAL name takes the game\'s UK figure');
    assert.equal(evalJson(`medianOf('Ratchet: Gladiator', 'US')`), 13.99);
    assert.equal(evalJson(`medianOf('Sly 3', 'UK')`), 9, 'a name with no source row keeps its own figures');
    // Times are on the 24-hour clock, in the visitor's own time zone (no zone is forced, so the browser picks theirs).
    for (const zone of ['Asia/Tokyo', 'America/New_York', 'Europe/London']) {
        const shown = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: zone }).format(new Date('2026-10-15T12:46:00Z'));
        assert.match(shown, /^\d{2}:\d{2}$/);
    }
    const stamped = evalJson(`formatLocalTime('2026-10-15 12:46:00 UTC')`);
    assert.match(stamped, /\b\d{2}:\d{2}\b/);
    assert.doesNotMatch(stamped, /\b(am|pm)\b/i, 'no 12-hour clock');
    assert.match(read('index.html'), /hourCycle: 'h23', timeZoneName: 'short'/);
    assert.doesNotMatch(read('index.html'), /formatLocalTime[^\n]*timeZone: '/, 'no fixed zone for the visitor\'s times');
    // Names of one game the library keeps apart share their figures, site by site (King's Field IV / The Ancient City).
    run(`setPrices({ games: {
        "King's Field IV": { level: 'normal', mentions: 1, US: { copies: 0, listed: 2, checked: '2026-10-15T10:00Z' }, UK: { copies: 6, median: 206.1, checked: '2026-10-15T10:00Z' } },
        "King's Field: The Ancient City": { level: 'normal', mentions: 0, US: { copies: 15, median: 119.99, checked: '2026-10-15T10:00Z' } },
        "King's Field IV: The Ancient City": { level: 'normal', mentions: 0, US: { unmatched: true }, UK: { unmatched: true } },
    } }, { same_game: [["King's Field IV", "King's Field IV: The Ancient City", "King's Field: The Ancient City"], 'nonsense', ['One only']] })`);
    assert.equal(evalJson(`medianOf("King's Field IV", 'US')`), 119.99, 'the PAL name takes the US name\'s US figure');
    assert.equal(evalJson(`medianOf("King's Field IV", 'UK')`), 206.1);
    assert.equal(evalJson(`medianOf("King's Field: The Ancient City", 'UK')`), 206.1, 'and the US name takes the UK figure');
    assert.equal(evalJson(`medianOf("King's Field: The Ancient City", 'US')`), 119.99, 'a name keeps a figure of its own');
    assert.equal(evalJson(`medianOf("King's Field IV: The Ancient City", 'US')`), 119.99);
    const watch = JSON.parse(read('ebay_watchlist.json'));
    assert.ok(Array.isArray(watch.same_game) && watch.same_game.every(names => Array.isArray(names) && names.length >= 2 && names.every(name => typeof name === 'string')));
    // A game released in one region only says so where its other price can never exist.
    run(`coverSame = {}; coverIndex = {
        'gregory horror show': ['Gregory Horror Show', ' (Korea)', ' (Europe) (En,Fr,De)'],
        'romancing saga': ['Romancing SaGa', ' (USA)', ' (USA)'],
        'kuon': ['Kuon', ' (USA)', ' (Europe) (En,Fr,De)'],
        'ratchet deadlocked': ['Ratchet - Deadlocked', ' (USA) (En,Fr,Es)', ' (USA) (En,Fr,Es)'],
        'okami': ['Okami', ' (Japan)', ' (Japan)'],
    }`);
    assert.equal(evalJson(`regionOnly('Gregory Horror Show')`), 'PAL');
    assert.equal(evalJson(`regionOnly('Romancing SaGa')`), 'US');
    assert.equal(evalJson(`regionOnly('Kuon')`), null, 'out in both');
    assert.equal(evalJson(`regionOnly('Okami')`), null, 'no US or PAL file at all says nothing');
    run(`renamedKeys = new Set(['ratchet deadlocked'])`);
    assert.equal(evalJson(`regionOnly('Ratchet: Deadlocked')`), null, 'a game with another name on another site is never called exclusive');
    assert.equal(evalJson(`regionOnly('Ratchet - Deadlocked')`), null);
    run(`setPrices({ games: { 'Gregory Horror Show': { level: 'normal', mentions: 1, UK: { copies: 12, median: 105, checked: '2026-10-15T10:00Z' } }, 'Romancing SaGa': { level: 'normal', mentions: 1, US: { copies: 90, median: 25, checked: '2026-10-15T10:00Z' } } } }, null)`);
    const quotes = name => evalJson(`shelfQuotesHtml(${JSON.stringify(name)})`);
    assert.match(quotes('Gregory Horror Show'), /<span class="shelf-flag">US<\/span><b>n\/a<\/b>/, 'PAL only: no US copy to price');
    assert.match(quotes('Romancing SaGa'), /<span class="shelf-flag">UK<\/span><b>n\/a<\/b>/, 'US only: no UK copy to price');
    assert.doesNotMatch(quotes('Gregory Horror Show'), /UK<\/span><b>n\/a/);
    assert.match(quotes('Kuon'), /US<\/span><b>&ndash;<\/b>/, 'released in both: a dash');
    run(`coverIndex = null; coverIndexState = 'idle'; coverSame = {}; renamedKeys = new Set()`);
    // Rarity: the fewest copies on UK or US; zero counts; never-checked games last; "scarce" at 10 or fewer.
    run(`setPrices({ games: {
        'God Hand': { level: 'normal', mentions: 3, UK: { copies: 40, listed: 41, median: 90, checked: '2026-10-14T10:00Z' }, US: { copies: 60, listed: 60, median: 120, checked: '2026-10-14T10:00Z' } },
        'Kuon': { level: 'normal', mentions: 1, UK: { copies: 6, listed: 7, median: 150, checked: '2026-10-14T10:00Z' } },
        'CY Girls': { level: 'normal', mentions: 1, UK: { copies: 2, listed: 2, median: 30, checked: '2026-10-14T10:00Z' } },
        'Final Fantasy X': { level: 'normal', mentions: 1, UK: { copies: 0, listed: 0, checked: '2026-10-14T10:00Z' } },
        'FIFA 2003': { level: 'normal', mentions: 1, US: { copies: 6, listed: 200, truncated: true, median: 9, checked: '2026-10-14T10:00Z' } },
        'Spyro: The Eternal Night': { level: 'normal', mentions: 1, UK: { copies: 1, listed: 34, median: 9, checked: '2026-10-14T10:00Z' } },
        'Old Row': { level: 'normal', mentions: 1, UK: { copies: 3, median: 9, checked: '2026-10-14T10:00Z' } },
        'Kingdom Hearts II': { level: 'normal', mentions: 1, UK: { unmatched: true, copies: 0 } },
    } }, null)`);
    assert.deepEqual(evalJson(`scarcity('Kuon')`), [6, 'UK']);
    assert.deepEqual(evalJson(`scarcity('God Hand')`), [40, 'UK']);
    assert.equal(evalJson(`scarcity('Kingdom Hearts II')`), null, 'search words that find nothing say nothing about rarity');
    assert.equal(evalJson(`scarcity('Dragon Quest')`), null);
    // A count that eBay's own count for the same search does not back is not trusted: it is too low
    // (another spelling, a sibling game), so no "scarce" tag and no place among the rarest.
    assert.equal(evalJson(`scarcity('FIFA 2003')`), null, 'eBay lists 200, we counted 6');
    assert.equal(evalJson(`scarcity('Spyro: The Eternal Night')`), null, 'eBay lists 34, we counted 1');
    assert.equal(evalJson(`scarcity('Old Row')`), null, 'a figure saved before "listed" existed is not vouched for');
    assert.equal(evalJson(`scarceTagHtml('FIFA 2003')`), '');
    assert.match(evalJson(`scarceTagHtml('Kuon')`), /href="https:\/\/www\.ebay\.co\.uk\/sch\/i\.html\?_nkw=Kuon%20ps2&amp;_sacat=139973&amp;LH_ItemCondition=2750%7C3000%7C4000%7C5000&amp;LH_BIN=1&amp;LH_PrefLoc=1"/, 'the tag opens the search it counts');
    assert.deepEqual(evalJson(`byRarity([{name:'Dragon Quest'},{name:'God Hand'},{name:'Kuon'},{name:'CY Girls'},{name:'Final Fantasy X'}]).map(g => g.name)`),
        ['Final Fantasy X', 'CY Girls', 'Kuon', 'God Hand', 'Dragon Quest']);
    assert.match(evalJson(`scarceTagHtml('Kuon')`), /scarce &middot; 6 for sale on eBay UK/);
    assert.match(evalJson(`scarceTagHtml('Final Fantasy X')`), /none for sale on eBay UK/);
    assert.equal(evalJson(`scarceTagHtml('God Hand')`), '');
    // The buttons reorder the list and say which order is on.
    // Relative to the real clock: setRecentSort() redraws with Date.now(), so fixed dates stop working a day later.
    const now = Date.now();
    const stamp = new Date(now - 3600000).toISOString().slice(0, 19).replace('T', ' ') + ' UTC';
    context.__rareItems = ['God Hand', 'Kuon', 'CY Girls', 'Dragon Quest'].map(name => ({ headline: name, source: 'r/ps2', feed: 'reddit:ps2', timestamp: stamp, link: 'https://example.com', matched_games: [name], matched_in: 'headline' }));
    run(`renderRecentGames(__rareItems, ${now})`);
    const order = () => [...el('todayList').innerHTML.matchAll(/class="recent-game[^"]*">([^<]+)</g)].map(m => m[1]);
    assert.deepEqual(order(), ['Kuon', 'God Hand', 'CY Girls', 'Dragon Quest'], 'most expensive first (UK median)');
    assert.equal(el('sortPrice').getAttribute('aria-pressed'), 'true');
    run(`setRecentSort('rare')`);
    assert.deepEqual(order(), ['CY Girls', 'Kuon', 'God Hand', 'Dragon Quest'], 'most rare first');
    assert.equal(el('sortRare').getAttribute('aria-pressed'), 'true');
    assert.equal(el('sortPrice').getAttribute('aria-pressed'), 'false');
    assert.match(el('todaySummary').textContent, /Most rare first/);
    assert.match(el('todayList').innerHTML, /scarce &middot; 2 for sale on eBay UK/);
    // The shelf is rarest first whichever order the list is in; the common game goes to the far end
    const shelfOrder = () => [...el('shelf').innerHTML.matchAll(/class="shelf-name">([^<]+)</g)].map(m => m[1]);
    assert.deepEqual(shelfOrder(), ['CY Girls', 'Kuon', 'God Hand', 'Dragon Quest']);
    // Under each box: US dollars, UK pounds and euros (a dash where nothing is priced); a euro figure is converted and marked ≈ when only UK or US has one
    const kuonBox = el('shelf').innerHTML.split('<li class="shelf-item">').find(box => box.includes('>Kuon<'));
    assert.match(kuonBox, /<span class="shelf-flag">US<\/span><b>&ndash;<\/b>/);
    assert.match(kuonBox, /<span class="shelf-flag">UK<\/span><b>£150<\/b>/);
    assert.match(kuonBox, /<span class="shelf-quote is-none" title="No copies priced"><span class="shelf-flag">EU<\/span>/, 'no rates loaded, no euro figure');
    run(`fxData = { date: '2026-10-14', rates: { USD: 0.86, GBP: 1.15 } }; renderShelf()`);
    assert.match(el('shelf').innerHTML.split('<li class="shelf-item">').find(box => box.includes('>Kuon<')), /<span class="shelf-flag">EU<\/span><b>≈€173<\/b>/, '150 pounds at 1.15');
    run(`fxData = null; renderShelf()`);
    run(`setRecentSort('price')`);
    assert.deepEqual(order(), ['Kuon', 'God Hand', 'CY Girls', 'Dragon Quest']);
    assert.deepEqual(shelfOrder(), ['CY Girls', 'Kuon', 'God Hand', 'Dragon Quest'], 'the shelf does not follow the list\'s buttons');
    run(`setPrices(null, null)`);
});

await check('the real library plus the extra names: every game once, FIFA 09 to 14 present, nothing in the extras the library already has', async () => {
    const base = JSON.parse(read('data/ps2_database.json'));
    const extra = JSON.parse(read('search_extra_titles.json'));
    assert.ok(Array.isArray(extra.titles) && extra.titles.length > 500 && extra.source && extra.checked);
    context.__base = base;
    context.__extra = extra.titles;
    const keys = (list) => evalJson(`${list}.map(priceKey)`);
    const inBase = new Set(keys('__base'));
    const repeated = extra.titles.filter((title, i) => inBase.has(keys('__extra')[i]));
    assert.deepEqual(repeated, [], 'a name in the extras is one the library lacks');
    assert.equal(new Set(keys('__extra')).size, extra.titles.length, 'no game twice in the extras');
    vm.runInContext('setLibrary([...__base, ...__extra])', context);
    const shown = evalJson('library.map(game => game.title)');
    const unique = evalJson('new Set(library.map(game => priceKey(game.title))).size');
    assert.equal(unique, shown.length, 'one entry per game');
    for (const query of ['medal of honor frontline', 'goblin commander', 'fifa 10', 'fifa 11', 'fifa 12', 'fifa 13', 'fifa 14', 'fifa 09']) {
        const found = evalJson(`suggestGames(${JSON.stringify(query)}, 20)`);
        assert.ok(found.length >= 1, `${query} finds something`);
        assert.equal(new Set(found.map(title => evalJson(`priceKey(${JSON.stringify(title)})`))).size, found.length, `${query}: no game listed twice`);
    }
    assert.equal(evalJson(`suggestGames('medal of honor frontline').length`), 1);
    assert.equal(evalJson(`suggestGames('goblin commander').length`), 1);
    assert.equal(evalJson(`suggestGames('godh')[0]`), 'God Hand');
    vm.runInContext('setLibrary([])', context);
});

await check('Most rare ranks figures that predate "listed", weighs Wikipedia collectibles, and the Demand Index v2 draws', async () => {
    const run = (code) => vm.runInContext(code, context);
    // The state right after "listed" was added: almost no figure has it yet. Ranking must still work.
    run(`setPrices({ games: {
        'The Punisher': { level: 'normal', mentions: 2, US: { copies: 18, median: 114.69, checked: '2026-10-14T10:00Z' }, UK: { copies: 21, median: 48, checked: '2026-10-14T10:00Z' } },
        'Grand Theft Auto III': { level: 'normal', mentions: 9, US: { copies: 400, median: 6, checked: '2026-10-14T10:00Z' }, UK: { copies: 300, median: 5, checked: '2026-10-14T10:00Z' } },
        'Black': { level: 'normal', mentions: 9, US: { copies: 150, median: 6, listed: 150, checked: '2026-10-14T10:00Z' } },
        'Kuon': { level: 'normal', mentions: 1, UK: { copies: 4, median: 150, checked: '2026-10-14T10:00Z' } },
        'Prince of Persia: Sands of Time': { level: 'normal', mentions: 1, UK: { copies: 27, listed: 170, median: 6, checked: '2026-10-14T10:00Z' } },
        'Spyro: The Eternal Night': { level: 'normal', mentions: 1, UK: { copies: 1, listed: 34, median: 9, checked: '2026-10-14T10:00Z' } },
    } }, null)`);
    assert.deepEqual(evalJson(`supplyOf('The Punisher')`), [18, 'US']);
    assert.deepEqual(evalJson(`supplyOf('Prince of Persia: Sands of Time')`), [170, 'UK'], 'eBay\'s own count when ours is lower');
    assert.equal(evalJson(`supplyOf('Nothing Priced')`), null);
    const names = (list) => evalJson(`byRarity(${JSON.stringify(list.map(name => ({ name })))}).map(game => game.name)`);
    const everyone = ['Grand Theft Auto III', 'Black', 'Not Priced', 'The Punisher', 'Prince of Persia: Sands of Time', 'Kuon', 'Spyro: The Eternal Night'];
    assert.deepEqual(names(everyone), ['Kuon', 'The Punisher', 'Spyro: The Eternal Night', 'Black', 'Prince of Persia: Sands of Time', 'Grand Theft Auto III', 'Not Priced'].map(x => x),
        'few copies first even when "listed" is missing; common games last');
    // Wikipedia: a game its article calls collectible leads its group, and one with no figure yet sits among the second group.
    run(`setWikiChecks({
        'The Punisher': { article: 'The Punisher (2005 video game)', game: true, ps2: true, collectible: ['rare', 'sought-after'] },
        'Not Priced': { article: 'Not Priced (video game)', game: true, ps2: true, collectible: ['collectible'] },
        'Retro': { article: 'Retro gaming', game: false, ps2: false, collectible: ['rare'] },
        'Empty': { article: 'Empty', game: true, ps2: true, collectible: [] } })`);
    assert.equal(evalJson(`collectibleOf('Retro')`), null, 'not a PS2 game article: ignored');
    assert.equal(evalJson(`collectibleOf('Empty')`), null);
    assert.deepEqual(evalJson(`collectibleOf('The Punisher').words`), ['rare', 'sought-after']);
    assert.deepEqual(names(everyone), ['Kuon', 'Not Priced', 'The Punisher', 'Spyro: The Eternal Night', 'Black', 'Prince of Persia: Sands of Time', 'Grand Theft Auto III'].map(x => x));
    assert.match(evalJson(`collectibleTagHtml('The Punisher')`), /href="https:\/\/en\.wikipedia\.org\/wiki\/The_Punisher_\(2005_video_game\)"[^>]*>collectible<\/a>/);
    assert.equal(evalJson(`collectibleTagHtml('Kuon')`), '');
    run(`setWikiChecks(null)`);
    run(`setPrices(null, null)`);

    // The Demand Index, version 2 and the old file both draw.
    const file = { version: 2, generated: '2026-10-14 10:00:00 UTC', recent_days: 3, youtube_views_seen: true, games: [
        { title: 'God Hand', demand: 71.2, mentions: 12, recent: 8, sources: 5, youtube_views: 1250000, ebay_change_pct: 12.5, trend_pct: -3.1 },
        { title: 'Kuon', demand: 40, mentions: 2, recent: 0, sources: 1, youtube_views: 0, ebay_change_pct: null, trend_pct: null }] };
    context.__demand = file;
    context.fetch = async () => ({ ok: true, json: async () => context.__demand });
    await vm.runInContext('loadDemand()', context);
    const html = el('demandList').innerHTML;
    assert.match(html, /God Hand/);
    assert.match(html, /12 mentions \(8 in the last 3 days\) · 5 sources · 1\.3M YouTube views · eBay ▲ 12\.5% · Wikipedia ▼ 3\.1%/);
    assert.match(html, /2 mentions \(0 in the last 3 days\) · 1 source · 0 YouTube views/);
    assert.doesNotMatch(html, /null|undefined|NaN/);
    assert.match(el('demandSummary').textContent, /Mentions rising/);
    context.fetch = fakeFetch;
});

await check('Library: every game once, A to Z or by genre, filtered, and a click adds it to My collection', async () => {
    const run = (code) => vm.runInContext(code, context);
    const kept = new Map();
    context.localStorage = { getItem: (key) => (kept.has(key) ? kept.get(key) : null), setItem: (key, value) => { kept.set(key, String(value)); } };
    run(`collection = []`);
    run(`setLibrary(['The Getaway', 'God Hand', '007: Agent Under Fire', 'Zone of the Enders', 'Gran Turismo 4', 'Kuon'])`);
    run(`genreData = { names: ['Action', 'Racing'], genres: { [priceKey('God Hand')]: 0, [priceKey('Gran Turismo 4')]: 1, [priceKey('Zone of the Enders')]: 0 } }; genreState = 'ready'; fillGenreMenu()`);
    run(`showView('library')`);
    assert.equal(el('viewLibrary').classList.contains('hidden'), false);
    assert.equal(el('tabLibrary').classList.contains('is-active'), true);
    run(`renderLibrary()`);
    assert.deepEqual(evalJson(`libraryShown.map(g => g.title)`), ['The Getaway', 'God Hand', 'Gran Turismo 4', 'Kuon', 'Zone of the Enders', '007: Agent Under Fire'],
        'A to Z, "The" ignored, titles starting with a digit last under #');
    assert.deepEqual(evalJson(`libraryShown.map(g => g.letter)`).slice(0, 2), ['G', 'G']);
    run(`setLibrarySort('genre')`);
    assert.deepEqual(evalJson(`libraryShown.map(g => g.title)`), ['God Hand', 'Zone of the Enders', 'Gran Turismo 4', '007: Agent Under Fire', 'The Getaway', 'Kuon'],
        'genres in the list\'s order, Other last, A to Z inside each');
    run(`setLibraryGenre('Racing')`);
    assert.deepEqual(evalJson(`libraryShown.map(g => g.title)`), ['Gran Turismo 4']);
    run(`setLibraryGenre('')`); run(`setLibrarySort('az')`);
    run(`setLibraryFilter('godhand')`);
    assert.deepEqual(evalJson(`libraryShown.map(g => g.title)`), ['God Hand'], 'the filter ignores spaces and punctuation');
    run(`setLibraryFilter('')`);

    // US and PAL exclusives, told from the box-art collection: a box for one region only.
    run(`coverIndex = { [priceKey('God Hand')]: ['God Hand', ' (USA)', ' (USA)'], [priceKey('Kuon')]: ['Kuon', ' (USA)', ' (Europe) (En,Fr,De)'],
        [priceKey('Gran Turismo 4')]: ['Gran Turismo 4', ' (Europe)', ' (Europe)'], [priceKey('Zone of the Enders')]: ['Zone of the Enders', ' (Japan)', ' (Japan)'],
        [priceKey('The Getaway')]: ['Getaway', ' (Europe, Australia)', ' (Europe, Australia)'] }; librarySorted = null`);
    run(`setLibraryRegion('US')`);
    assert.deepEqual(evalJson(`libraryShown.map(g => g.title)`), ['God Hand'], 'an American box and no European one');
    run(`setLibraryRegion('PAL')`);
    assert.deepEqual(evalJson(`libraryShown.map(g => g.title)`), ['The Getaway', 'Gran Turismo 4'], 'a European box and no American one; Kuon (both) and a Japan-only game are neither');
    assert.equal(el('libRegionPal').getAttribute('aria-pressed'), 'true');
    assert.match(el('libraryNote').textContent, /PAL exclusive means the box-art collection has only a European box/);
    run(`setLibraryRegion('')`);
    assert.equal(evalJson(`libraryShown.length`), 6, 'all regions: every game again');
    run(`coverIndex = null; librarySorted = null; coverIndexState = 'ready'; setLibraryRegion('US')`);
    assert.deepEqual(evalJson(`libraryShown.map(g => g.title)`), [], 'without the list of regions nothing can be told apart');
    run(`setLibraryRegion(''); coverIndexState = 'idle'; librarySorted = null`);

    // Regional and misspelt names of one game are one tile; adding picks the spelling eBay has a price for in that region
    run(`setLibrary(['Project Zero', 'Fatal Frame', 'God Hand', 'Alien Homind', 'Alien Hominid'])`);
    run(`coverSame = { [priceKey('Fatal Frame')]: priceKey('Project Zero'), [priceKey('Alien Homind')]: priceKey('Alien Hominid') }; librarySorted = null`);
    run(`setPrices({ currencies: { UK: 'GBP', US: 'USD' }, games: {
        'Fatal Frame': { level: 'normal', mentions: 1, US: { copies: 5, median: 40, checked: '2026-10-14T10:00Z' } },
        'Project Zero': { level: 'normal', mentions: 1, UK: { copies: 4, median: 30, checked: '2026-10-14T10:00Z' } } } }, null)`);
    run(`renderLibrary()`);
    assert.deepEqual(evalJson(`libraryShown.map(g => g.title)`), ['Alien Hominid', 'God Hand', 'Project Zero'], 'two spellings, one tile; the shown spelling is the one the file names');
    assert.deepEqual(evalJson(`libraryShown.find(g => g.title === 'Project Zero').variants.sort()`), ['Fatal Frame', 'Project Zero']);
    assert.equal(evalJson(`libraryEntries().flatMap(g => g.variants).length`), 5, 'folding keeps every name of the library: five names, four tiles');
    assert.equal(run(`libraryTitleFor(libraryShown[2], 'US')`), 'Fatal Frame', 'a US copy is filed under the name the US site prices');
    assert.equal(run(`libraryTitleFor(libraryShown[2], 'PAL')`), 'Project Zero');
    assert.equal(run(`libraryTitleFor(libraryShown[1], 'PAL')`), 'God Hand', 'no price anywhere: the shown name');
    run(`libraryPick(2)`); el('libraryAddRegion').value = 'US'; el('libraryAddCondition').value = 'loose'; run(`libraryAddPicked()`);
    assert.deepEqual(evalJson(`collection.map(e => [e.title, e.region])`), [['Fatal Frame', 'US']]);
    run(`renderLibrary()`);
    assert.match(el('libraryGrid').innerHTML, /lib-tile is-owned/, 'the one tile shows as owned whichever spelling is in the collection');
    run(`collection = []; libraryClosePicked(); coverSame = {}; librarySorted = null`);
    run(`setLibrary(['The Getaway', 'God Hand', '007: Agent Under Fire', 'Zone of the Enders', 'Gran Turismo 4', 'Kuon'])`);
    run(`genreData = { names: ['Action', 'Racing'], genres: { [priceKey('God Hand')]: 0, [priceKey('Gran Turismo 4')]: 1, [priceKey('Zone of the Enders')]: 0 } }; renderLibrary()`);

    // A click opens the bar; adding goes to My collection and marks the tile
    run(`libraryPick(1)`);
    assert.equal(el('libraryAdd').classList.contains('hidden'), false);
    assert.equal(el('libraryAddName').textContent, 'God Hand');
    el('libraryAddRegion').value = 'US'; el('libraryAddCondition').value = 'loose';
    run(`libraryAddPicked()`);
    assert.deepEqual(evalJson(`collection.map(e => [e.title, e.region, e.condition, e.qty])`), [['God Hand', 'US', 'loose', 1]]);
    assert.match(el('libraryAddMessage').textContent, /^Added: God Hand \(US, .*\)\. You now own 1\.$/);
    run(`renderLibrary()`);
    assert.match(el('libraryGrid').innerHTML, /lib-tile is-owned/);
    run(`libraryPick(1)`); run(`libraryAddPicked()`);
    assert.equal(evalJson(`collection[0].qty`), 2, 'the same copy again raises the count');
    run(`showView('dashboard')`);
    assert.equal(el('libraryAdd').classList.contains('hidden'), true, 'the bar closes when the page is left');
    run(`collection = []`);
});

await check('My collection: add, value, keep in the browser, back up and restore; reference prices; installable', async () => {
    const run = (code) => vm.runInContext(code, context);
    const kept = new Map();
    context.localStorage = { getItem: (key) => (kept.has(key) ? kept.get(key) : null), setItem: (key, value) => { kept.set(key, String(value)); } };
    run(`setLibrary(['God Hand', 'Kuon', 'Rule of Rose', 'Black'])`);
    run(`setPrices({ currencies: { UK: 'GBP', US: 'USD' }, games: {
        'God Hand': { level: 'normal', mentions: 1, US: { copies: 30, median: 100, complete: { copies: 12, median: 130 }, checked: '2026-10-14T10:00Z' },
                      UK: { copies: 9, median: 60, checked: '2026-10-14T10:00Z' } },
        'Kuon': { level: 'normal', mentions: 1, US: { copies: 3, median: 1000, unmatched: true, checked: '2026-10-14T10:00Z' } },
    } }, null)`);
    run(`referenceData = { sources: { a: { name: 'Example Site, a list', url: 'https://example.com/a', published: '2026-07-14' }, b: { name: 'Old Site', url: 'https://example.com/b', published: '2023-06-02' } },
        prices: [ { title: 'Rule of Rose', region: 'US', condition: 'sealed', price: 1160, currency: 'USD', source: 'a' },
                  { title: 'Rule of Rose', region: 'US', condition: 'complete', price: 1000, currency: 'USD', source: 'a' },
                  { title: 'Rule of Rose', region: '?', condition: 'mint', price: 650, currency: 'GBP', source: 'b' },
                  { title: 'Rule of Rose', region: 'PAL', condition: 'mint', price: 400, currency: 'USD', source: 'b', note: 'PAL list takes GBP or PAL-region points' } ] }`);

    // Adding, merging, validation
    assert.equal(run(`collection.length`), 0);
    assert.equal(run(`addToCollection('God Hand', 'US', 'complete', 2, 90)`), true);
    assert.equal(run(`addToCollection('God Hand', 'US', 'complete', 1)`), true, 'the same game, region and condition adds a copy');
    assert.equal(run(`addToCollection('God Hand', 'PAL', 'loose')`), true);
    assert.equal(run(`addToCollection('Kuon', 'US', 'loose')`), true);
    assert.equal(run(`addToCollection('Rule of Rose', 'US', 'sealed')`), true);
    assert.equal(run(`addToCollection('', 'US', 'loose')`), false);
    assert.equal(run(`addToCollection('God Hand', 'MARS', 'loose')`), false);
    assert.equal(run(`addToCollection('God Hand', 'US', 'mint')`), false);
    assert.deepEqual(evalJson(`collection.map(e => [e.title, e.region, e.condition, e.qty, e.paid])`),
        [['God Hand', 'US', 'complete', 3, 90], ['God Hand', 'PAL', 'loose', 1, null], ['Kuon', 'US', 'loose', 1, null], ['Rule of Rose', 'US', 'sealed', 1, null]]);
    assert.deepEqual(JSON.parse(kept.get('ps2-sentiment-tracker.collection')).length, 4, 'saved in the browser');

    // Values: complete uses the complete median, loose the overall one, an unmatched figure none, sealed an article price
    assert.deepEqual(evalJson(`collectionValue(collection[0])`), [130, 'USD', 'ebay']);
    assert.deepEqual(evalJson(`collectionValue(collection[1])`), [60, 'GBP', 'ebay']);
    assert.deepEqual(evalJson(`collectionValue(collection[2])`), [null, 'USD', 'none']);
    assert.deepEqual(evalJson(`collectionValue(collection[3])`), [1160, 'USD', 'article']);
    assert.deepEqual(evalJson(`collectionTotals()`), { worth: { USD: 130 * 3 + 1160, GBP: 60 }, paid: { USD: 270 }, unpriced: 1, copies: 6 });
    run(`showView('collection')`);
    assert.equal(el('viewCollection').classList.contains('hidden'), false);
    assert.equal(el('tabCollection').classList.contains('is-active'), true);
    assert.equal(el('viewRare').classList.contains('hidden'), true);
    assert.match(el('collectionSummary').textContent, /^4 games, 6 copies\. Estimated value \$1,550 \+ £60\.00 \(1 copy without a price\)\.$/);
    const html = el('collectionList').innerHTML;
    assert.match(html, /God Hand/); assert.match(html, /×3/); assert.match(html, /paid \$90/); assert.match(html, /no price/);
    assert.match(html, /class="coll-tile"/, 'cover tiles');
    assert.match(html, /<span class="coll-initials" aria-hidden="true">GH<\/span>/, 'a tile without a cover shows the initials');
    assert.doesNotMatch(html, /<img/, 'no cover asked for yet, so no image');
    assert.doesNotMatch(html, /NaN|undefined|null/);
    assert.deepEqual([el('tabCollectionCount').textContent, el('tabCollectionCount').classList.contains('hidden')], ['6', false]);

    // The form: only a name from the library is accepted
    el('collectionGame').value = 'kuo'; el('collectionRegion').value = 'PAL'; el('collectionCondition').value = 'complete'; el('collectionQty').value = '2'; el('collectionPaid').value = '';
    run(`onCollectionInput()`);
    assert.match(el('collectionSuggest').innerHTML, /role="option"[^>]*>Kuon<\/li>/, 'the same kind of dropdown as the main search');
    assert.equal(el('collectionSuggest').classList.contains('hidden'), false);
    // Keyboard: arrows move, Enter fills the name in, Escape closes
    run(`onCollectionKey({ key: 'ArrowDown' })`);
    assert.equal(run(`collectionSuggestAt`), 0);
    run(`onCollectionKey({ key: 'Enter' })`);
    assert.equal(el('collectionGame').value, 'Kuon');
    assert.equal(el('collectionSuggest').classList.contains('hidden'), true, 'the list closes once a name is picked');
    el('collectionGame').value = 'god'; run(`onCollectionInput()`);
    run(`onCollectionKey({ key: 'Escape' })`);
    assert.equal(el('collectionSuggest').classList.contains('hidden'), true);
    el('collectionGame').value = 'kuo'; run(`onCollectionInput()`);
    run(`pickCollectionSuggestion(0)`);
    assert.equal(el('collectionGame').value, 'Kuon');
    run(`addFromForm()`);
    assert.match(el('collectionMessage').textContent, /Added Kuon/);
    assert.equal(run(`collection.find(e => e.title === 'Kuon' && e.region === 'PAL').qty`), 2);
    el('collectionGame').value = 'zzzz nothing';
    run(`addFromForm()`);
    assert.match(el('collectionMessage').textContent, /No PS2 game by that name/);
    assert.equal(run(`collection.length`), 5);

    // Survives a reload: a fresh load reads what was kept; garbage is ignored
    run(`collection = []; loadCollection()`);
    assert.equal(run(`collection.length`), 5);
    kept.set('ps2-sentiment-tracker.collection', '{not json');
    run(`loadCollection()`);
    assert.equal(run(`collection.length`), 0, 'a damaged save is treated as empty, not an error');
    kept.set('ps2-sentiment-tracker.collection', JSON.stringify([{ title: 'God Hand', region: 'US', condition: 'loose', qty: 500, paid: -3 }, { title: '<img src=x onerror=1>', region: 'PAL', condition: 'loose', qty: 1 }, 7, null]));
    run(`loadCollection()`);
    assert.deepEqual(evalJson(`collection.map(e => [e.title, e.qty, e.paid])`), [['God Hand', 99, null], ['<img src=x onerror=1>', 1, null]], 'quantity capped, a negative price dropped');
    run(`renderCollection()`);
    assert.doesNotMatch(el('collectionList').innerHTML, /<img src=x/, 'a title is never markup');

    // Backup file round trip, and a stranger's file is refused
    run(`collection = []; addToCollection('God Hand', 'US', 'loose', 2, 50); addToCollection('Kuon', 'PAL', 'complete')`);
    const file = run(`exportCollection()`);
    const backup = JSON.parse(file);
    assert.deepEqual([backup.app, backup.kind, backup.version, backup.games.length], ['ps2-sentiment-tracker', 'collection', 1, 2]);
    run(`collection = []`);
    assert.equal(run(`loadCollectionFile(${JSON.stringify(file)})`), 2);
    assert.deepEqual(evalJson(`collection.map(e => [e.title, e.qty, e.paid])`), [['God Hand', 2, 50], ['Kuon', 1, null]]);
    assert.equal(run(`loadCollectionFile('not a backup')`), -1);
    assert.equal(run(`loadCollectionFile('{"hello": 1}')`), -1);
    assert.equal(run(`collection.length`), 2, 'a refused file changes nothing');
    run(`removeFromCollection(0)`);
    assert.deepEqual(evalJson(`collection.map(e => e.title)`), ['Kuon']);
    run(`removeFromCollection(99)`);
    assert.equal(run(`collection.length`), 1);

    // Storage that refuses: it still works for the session and says so
    context.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
    run(`loadCollection(); collection = []; addToCollection('God Hand', 'US', 'loose')`);
    assert.equal(run(`collection.length`), 1);
    assert.equal(run(`collectionKept`), false);
    run(`renderCollection()`);
    assert.match(el('collectionNote').textContent, /would not store the list/);
    context.localStorage = { getItem: () => null, setItem() {} };
    run(`collection = []; collectionKept = true; updateCollectionTab()`);


    // Covers: covers.json names the Libretro box-art file for each game; the browser asks for the picture itself
    context.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
    const BASE = 'https://thumbnails.libretro.com/Sony%20-%20PlayStation%202/Named_Boxarts/';
    const index = { what: 'x', covers: {
        'god hand': ['God Hand', ' (USA)', ' (Europe) (En,Fr,De,Es,It)'],
        'ratchet clank': ['Ratchet _ Clank', ' (USA) (En,Fr,De,Es,It)', ' (Europe) (En,Fr,De,Es,It) (v1.00)'],
        kuon: ['Kuon', ' (USA)', ''],
        'only pal': ['Only Pal', '', ' (Europe)'],
        'bad entry': ['', ' (USA)', ''], 'worse entry': 'nope',
    } };
    const asked = [];
    let answer = { ok: true, json: async () => index };
    context.fetch = async (url) => { asked.push(String(url)); return answer; };
    run(`coversShown = true; coverIndex = null; coverIndexState = 'idle'`);
    assert.equal(run(`coverUrl('God Hand')`), '', 'nothing until the index is read');
    assert.equal(run(`coverNote('God Hand')`), 'looking for a cover…');
    run(`collection = []; addToCollection('God Hand', 'US', 'complete'); addToCollection('God Hand', 'PAL', 'loose'); addToCollection('Ratchet & Clank', 'US', 'loose'); addToCollection('Black', 'US', 'loose'); renderCollection()`);
    await new Promise(done => setTimeout(done, 20));
    assert.deepEqual(asked, ['covers.json'], 'the index is read once, and only when a cover is wanted');
    assert.equal(run(`coverIndexState`), 'ready');
    assert.equal(run(`coverUrl('God Hand')`), `${BASE}God%20Hand%20(USA).png`);
    assert.equal(run(`coverUrl('God Hand', 'PAL')`), `${BASE}God%20Hand%20(Europe)%20(En%2CFr%2CDe%2CEs%2CIt).png`, 'a PAL copy gets the PAL box');
    assert.equal(run(`coverUrl('Ratchet & Clank')`), `${BASE}Ratchet%20_%20Clank%20(USA)%20(En%2CFr%2CDe%2CEs%2CIt).png`, 'spelt the way the collection spells it');
    assert.equal(run(`coverUrl('Kuon', 'PAL')`), `${BASE}Kuon%20(USA).png`, 'the other region\'s box when there is no PAL one');
    assert.equal(run(`coverUrl('Only Pal', 'US')`), `${BASE}Only%20Pal%20(Europe).png`);
    for (const none of ['Black', 'Bad Entry', 'Worse Entry', '', null, 'constructor', '__proto__']) assert.equal(run(`coverUrl(${JSON.stringify(none)})`), '', `no cover for ${JSON.stringify(none)}`);
    assert.ok(run(`coverUrl('God Hand')`).startsWith('https://thumbnails.libretro.com/'), 'only the collection\'s own address is ever built');
    const tiles = el('collectionList').innerHTML;
    assert.match(tiles, /<img src="https:\/\/thumbnails\.libretro\.com\/Sony%20-%20PlayStation%202\/Named_Boxarts\/God%20Hand%20\(USA\)\.png"[^>]*referrerpolicy="no-referrer"/);
    assert.match(tiles, /God%20Hand%20\(Europe\)/);
    assert.match(tiles, /<span class="coll-initials" aria-hidden="true">B<\/span>/, 'a game without a cover keeps its initials');
    assert.match(tiles, /no cover in the Libretro thumbnail collection/);
    // The game's page shows the box beside its title
    el('gameCover').classList.add('hidden');
    run(`renderGamePage('God Hand')`);
    assert.match(el('gameCover').innerHTML, /<img src="https:\/\/thumbnails\.libretro\.com\/[^"]*God%20Hand%20\(USA\)\.png"/);
    assert.equal(el('gameCover').classList.contains('hidden'), false);
    run(`renderGamePage('Black')`);
    assert.equal(el('gameCover').innerHTML, '');
    assert.equal(el('gameCover').classList.contains('hidden'), true, 'no cover, no empty frame');
    // Switching covers off shows none and asks for none
    asked.length = 0;
    run(`setCoversShown(false)`);
    assert.doesNotMatch(el('collectionList').innerHTML, /<img/);
    assert.equal(run(`coverUrl('God Hand')`), '');
    assert.equal(el('gameCover').classList.contains('hidden'), true);
    assert.equal(asked.length, 0);
    assert.doesNotMatch(el('collectionNote').textContent, /libretro/);
    run(`setCoversShown(true)`);
    assert.match(el('collectionNote').textContent, /thumbnails\.libretro\.com .* names the game and shows that site your address/, 'the page says what leaves the browser');
    // An index that cannot be read leaves initials and says so; a bad file is not trusted
    for (const bad of [{ ok: false, status: 404, json: async () => ({}) }, { ok: true, json: async () => ({ covers: [] }) }, { ok: true, json: async () => ({ covers: null }) }, { ok: true, json: async () => { throw new SyntaxError('x'); } }]) {
        answer = bad;
        run(`coverIndex = null; coverIndexState = 'idle'; renderCollection()`);
        await new Promise(done => setTimeout(done, 20));
        assert.equal(run(`coverIndexState`), 'failed');
        assert.equal(run(`coverUrl('God Hand')`), '');
        assert.equal(run(`coverNote('God Hand')`), 'cover list could not be loaded (offline or blocked)');
        assert.doesNotMatch(el('collectionList').innerHTML, /<img/);
    }
    // The real index: well-known games are in it, and every entry builds an address
    const real = JSON.parse(read('covers.json'));
    answer = { ok: true, json: async () => real };
    run(`coverIndex = null; coverIndexState = 'idle'; ensureCoverIndex()`);
    await new Promise(done => setTimeout(done, 20));
    for (const name of ['God Hand', 'Okami', 'Silent Hill 2', 'Kingdom Hearts II', 'The Getaway', 'Ratchet & Clank', 'Shadow of the Colossus', 'Kuon']) {
        assert.match(run(`coverUrl(${JSON.stringify(name)})`), /^https:\/\/thumbnails\.libretro\.com\/Sony%20-%20PlayStation%202\/Named_Boxarts\/[^"<>]+\.png$/, `${name} has a cover`);
    }
    assert.ok(Object.keys(real.covers).length > 4000, 'thousands of games');
    assert.ok(Object.values(real.covers).every(value => Array.isArray(value) && value.length === 3 && typeof value[0] === 'string' && value[0] && value.slice(1).every(part => typeof part === 'string') && (value[1] || value[2])), 'every entry has a title and a region');
    // Pictures kept with the site (covers/) beat the collection's file, for every region, and exist on disk
    for (const [name, file] of [['Final Fantasy X', 'covers/final-fantasy-x.jpg'], ['The Silent Hill Collection', 'covers/silent-hill-collection.jpg'],
        ['Grand Theft Auto: The Trilogy', 'covers/grand-theft-auto-the-trilogy.jpg'], ['Deutsch Rock-Pop', 'covers/singstar-deutsch-rock-pop.jpg']]) {
        assert.equal(run(`coverUrl(${JSON.stringify(name)})`), file, name);
        assert.equal(run(`coverUrl(${JSON.stringify(name)}, 'PAL')`), file, `${name}, PAL`);
        assert.equal(run(`coverNote(${JSON.stringify(name)})`), 'cover kept with this site');
        assert.ok(existsSync(new URL(file, root)), `${file} exists`);
    }
    assert.equal(Object.keys(real.local).length, 8);
    assert.ok(Object.values(real.local).every(file => /^covers\/[\w.-]+\.jpg$/.test(file) && existsSync(new URL(file, root))));
    // Most mentioned and Rarest rows carry a small box beside them, and only when there is one
    const wrapped = run(`withCover('God Hand', 'US', '<b>row</b>')`);
    assert.match(wrapped, /^<div class="row-cover-wrap"><img class="row-cover" src="https:\/\/thumbnails\.libretro\.com\/[^"]*God%20Hand%20\(USA\)\.png"[^>]*referrerpolicy="no-referrer"[^>]*><div class="row-cover-body"><b>row<\/b><\/div><\/div>$/);
    assert.equal(run(`withCover('Nothing Known Here', 'US', '<b>row</b>')`), '<b>row</b>', 'no cover, the row as it was');
    assert.match(run(`withCover('Obscure PAL Name', 'PAL', 'x', 'God Hand')`), /God%20Hand%20\(Europe\)/, "the list's other title is tried too");
    assert.match(run(`withCover('God Hand', 'PAL', 'x')`), /God%20Hand%20\(Europe\)/, 'a PAL list gets the PAL box');
    const item = (game) => ({ headline: `${game} news`, source: 'Eurogamer', link: 'https://e.example/', matched_game: game, sentiment: 50, timestamp: '2026-10-01 10:00 UTC' });
    context.__games = [item('God Hand'), item('God Hand'), item('Nothing Known Here')];
    run(`renderTopGames(__games)`);
    const topRows = el('topGamesList').innerHTML.split('<li ').slice(1);
    assert.match(topRows[0], /class="row-cover"[^>]*God%20Hand/);
    assert.doesNotMatch(topRows[1], /row-cover/);
    run(`setCoversShown(false)`);
    assert.doesNotMatch(el('topGamesList').innerHTML, /row-cover/, 'covers off: no pictures in the lists either');
    run(`setCoversShown(true)`);
    // The index arriving redraws the lists that were drawn without it
    run(`coverIndex = null; coverIndexState = 'idle'; renderTopGames(__games)`);
    assert.doesNotMatch(el('topGamesList').innerHTML, /row-cover/);
    run(`ensureCoverIndex()`);
    await new Promise(done => setTimeout(done, 20));
    assert.match(el('topGamesList').innerHTML, /class="row-cover"/, 'drawn again once the covers list has arrived');
    assert.match(read('index.html'), /if \(view === 'rare' \|\| view === 'mentions' \|\| view === 'demand' \|\| view === 'library' \|\| view === 'gacha' \|\| view === 'underrated'\) ensureCoverIndex\(\);/, 'opening any of these pages asks for the covers list');
    assert.equal(run(`initialsOf('The Legend of Heroes: Trails')`), 'TLO');
    context.fetch = fakeFetch;
    context.localStorage = { getItem: () => null, setItem() {} };

    // The address "#collection" opens the page
    context.location.hash = '#collection';
    assert.equal(run(`showViewFromAddress()`), 'collection');
    context.location.hash = '';
    run(`showView('dashboard', false)`);

    // Reference prices under a rare game: the US list takes USD points, the PAL list GBP or PAL ones
    const us = run(`referenceHtml('Rule of Rose', 'US', 'en-US')`);
    assert.match(us, /Articles \(not live\): \$1,000 complete \(<a href="https:\/\/example\.com\/a"[^>]*>Example Site<\/a> 2026\)/);
    assert.doesNotMatch(us, /£650/);
    const pal = run(`referenceHtml('Rule of Rose', 'PAL', 'en-US')`);
    assert.match(pal, /£650 mint/);
    assert.doesNotMatch(pal, /\$400/, 'one figure per article');
    assert.doesNotMatch(pal, /Example Site/, 'a US point is not shown on the PAL list');
    assert.equal(run(`referenceHtml('Nothing Here', 'US', 'en-US')`), '');
    run(`referenceData = null`);
    assert.equal(run(`referenceHtml('Rule of Rose', 'US', 'en-US')`), '');

    // The My collection button sits in the header beside REFRESH, not among the page tabs
    const pageHtml = read('index.html');
    const header = pageHtml.slice(pageHtml.indexOf('<div class="brand-actions">'), pageHtml.indexOf('<div class="brand-lock">'));
    assert.ok(header.indexOf('onclick="fetchSentimentData()"') < header.indexOf('id="tabCollection"'), 'after REFRESH');
    assert.match(header, /id="tabCollection"[^>]*onclick="showView\('collection'\)"[^>]*class="brand-btn brand-btn-collection"/);
    const tabs = pageHtml.slice(pageHtml.indexOf('<div class="view-tabs"'), pageHtml.indexOf('</div>', pageHtml.indexOf('<div class="view-tabs"')));
    assert.doesNotMatch(tabs, /tabCollection/, 'no longer one of the page tabs');
    run(`showView('collection')`);
    assert.equal(el('tabCollection').classList.contains('is-active'), true);
    run(`showView('rare')`);
    assert.equal(el('tabCollection').classList.contains('is-active'), false);
    // The button is a yellow outline (the keepsake colour): yellow text on its own dark yellow ground stays readable
    const cssText = read('retro.css');
    const tok = Object.fromEntries([...cssText.matchAll(/--([a-z-]+):\s*(#[0-9A-Fa-f]{6})/g)].map(m => [m[1], m[2]]));
    const lum = (hex) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
    const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
    assert.ok(ratio(tok.money, tok['money-bg']) >= 4.5, 'yellow on its dark ground');
    assert.ok(ratio(tok.bg, tok.money) >= 4.5, 'the count: dark on yellow');
    assert.doesNotMatch(cssText, /collection-shine|linear-gradient\(135deg, var\(--accent-hi\)/, 'no glossy gradient or shine any more');
    assert.match(cssText, /body \.brand-btn-collection \{[^}]*border-color: var\(--money-line\);[^}]*color: var\(--money\)/);

    // The files that make the site installable
    const manifest = JSON.parse(read('manifest.webmanifest'));
    assert.equal(manifest.start_url, './'); assert.equal(manifest.display, 'standalone');
    for (const icon of manifest.icons) assert.ok(existsSync(new URL(icon.src, root)), `${icon.src} exists`);
    assert.ok(manifest.icons.some(icon => icon.sizes === '192x192') && manifest.icons.some(icon => icon.sizes === '512x512'));
    const page = read('index.html');
    assert.match(page, /<link rel="manifest" href="manifest\.webmanifest">/);
    assert.match(page, /<link rel="apple-touch-icon" href="icons\/icon-180\.png">/);
    const worker = read('sw.js');
    assert.match(worker, /url\.origin !== self\.location\.origin\) return;/, 'only our own files go through the worker');
    assert.match(worker, /request\.method !== 'GET'/);
    assert.match(worker, /fetch\(request\)[\s\S]*\.catch\(\(\) => caches\.match\(request\)/, 'network first, the saved copy only when it fails');
    assert.doesNotMatch(worker, /localStorage|indexedDB/, 'the worker holds nothing of the visitor\'s');
});

await check('speed: formatters are made once, and a page that is not on screen is drawn when it is opened', async () => {
    const run = (code) => vm.runInContext(code, context);
    // One formatter per kind, however many prices are drawn
    run(`formatCache.clear()`);
    for (let i = 0; i < 50; i++) run(`money(${i + 1.5}, 'GBP', 'en-GB')`);
    assert.equal(run(`formatCache.size`) <= 2, true, 'a price drawn 50 times made at most one formatter per digit style');
    assert.equal(run(`money(1234.5, 'USD', 'en-US')`), '$1,235');
    assert.equal(run(`money(52.7, 'GBP', 'en-GB')`), '£52.70');
    // In a browser (requestIdleCallback exists) a hidden page's long list waits for its tab
    context.window.requestIdleCallback = () => {};
    try {
        run(`showView('dashboard', false)`);
        run(`setPrices({ currencies: { UK: 'GBP', US: 'USD' }, games: { 'God Hand': { level: 'normal', mentions: 1, US: { copies: 5, median: 100, checked: '2026-10-14T10:00Z' } } } }, null)`);
        el('pricesList').innerHTML = 'old';
        run(`renderPrices()`);
        assert.equal(el('pricesList').innerHTML, 'old', 'the eBay prices page is not on screen, so its rows are not built');
        assert.equal(el('tabPricesCount').textContent, '1', 'but its tab still says how many games');
        assert.match(el('pricesSummary').textContent, /1 games/);
        run(`showView('prices', false)`);
        assert.match(el('pricesList').innerHTML, /God Hand/, 'opening the page draws it');
        // on screen it is drawn at once, and a newer draw replaces a waiting one
        run(`renderPrices()`);
        assert.match(el('pricesList').innerHTML, /God Hand/);
        run(`showView('dashboard', false)`);
        el('topGamesList').innerHTML = 'old';
        run(`renderTopGames([{ headline: 'x', matched_game: 'God Hand', timestamp: '2026-10-14 10:00:00 UTC', source: 's' }])`);
        assert.equal(el('topGamesList').innerHTML, 'old');
        assert.equal(el('tabMentionsCount').textContent, '1');
        run(`showView('mentions', false)`);
        assert.match(el('topGamesList').innerHTML, /God Hand/);
    } finally {
        delete context.window.requestIdleCallback;
        run(`showView('dashboard', false)`);
        run(`setPrices(null, null)`);
    }
});

await check('editions: a game page lists its editions with their own prices and sources; the eBay list leaves them out', async () => {
    const run = (code) => vm.runInContext(code, context);
    const file = JSON.parse(read('editions.json'));
    run(`editionsData = ${JSON.stringify(file)}`);
    try {
        run(`setPrices({ currencies: { UK: 'GBP', US: 'USD' },
            games: { 'Resident Evil 4': { level: 'normal', mentions: 3, US: { copies: 9, median: 20, lowest: 10, checked: '2026-10-14T10:00Z' } },
                     'Resident Evil 4 Limited Edition': { kind: 'edition', level: 'rare', sites: ['UK'], UK: { copies: 2, median: 85, lowest: 70, checked: '2026-10-14T10:00Z' } } },
            editions: { PAL: { 'Resident Evil 4 Limited Edition': 'Resident Evil 4 Limited Edition' }, US: {} } }, null)`);
        const found = run(`editionsOfGame('Resident Evil 4').map(item => item.edition.title)`);
        assert.deepEqual(Array.from(found).sort(), ['Resident Evil 4 Collector\'s Pack', 'Resident Evil 4 Limited Edition', 'Resident Evil 4 Premium Edition']);
        assert.equal(run(`editionsOfGame('Silent Hill 2').length`), 0);
        const html = run(`editionsHtml('Resident Evil 4', Date.parse('2026-10-14T11:00Z'), 'en-GB')`);
        assert.match(html, /Editions of this game/);
        assert.match(html, /Resident Evil 4 Limited Edition/);
        assert.match(html, /£85/, 'the edition has its own UK price');
        assert.match(html, /FuturePress/, 'and its contents');
        assert.match(html, /href="https:\/\/collectorsedition\.org\/game-db\?c=PS2&amp;e=PAL"/, 'and a link to its source');
        assert.match(html, /Premium Edition[\s\S]*not checked yet/, 'an edition not priced yet says so');
        assert.doesNotMatch(run(`priceRows(priceData).map(row => row.title).join('|')`), /Limited Edition/, 'editions are not on the eBay prices list');
        assert.equal(run(`editionsHtml('Silent Hill 2')`), '');
        run(`editionsData = { lists: { PAL: [{ title: 3, game: 'Kuon' }, null, { title: 'x', game: 'Kuon', contents: '<b>' }] } }`);
        assert.match(run(`editionsHtml('Kuon')`), /&lt;b&gt;/, 'odd data is escaped, and an entry without a title is skipped');
    } finally {
        run(`editionsData = null`);
        run(`setPrices(null, null)`);
    }
});

await check('editions: the search finds them by name and by "steelbook", and My collection values them at their own price', async () => {
    const run = (code) => vm.runInContext(code, context);
    const file = JSON.parse(read('editions.json'));
    run(`editionsData = ${JSON.stringify(file)}`);
    const saved = run(`JSON.stringify(library.map(game => game.title))`);
    try {
        run(`setLibrary(['Resident Evil 4', 'God Hand', ...editionTitles()]); addEditionKeywords()`);
        const names = run(`suggestGames('resident evil 4', 8)`);
        assert.ok(names.includes('Resident Evil 4 Limited Edition') && names.includes('Resident Evil 4 Premium Edition'), 'both steelbook editions are in the search');
        const steel = run(`suggestGames('steelbook', 20)`);
        assert.ok(steel.includes('Resident Evil 4 Limited Edition') && steel.includes('Final Fantasy XII Collector\'s Edition'), 'typing steelbook finds steelbook editions');
        assert.ok(!steel.includes('God Hand') && !steel.includes('Resident Evil 4'), 'and not a plain copy');
        run(`setPrices({ currencies: { UK: 'GBP', US: 'USD' }, games: {
            'Resident Evil 4 Limited Edition': { kind: 'edition', level: 'rare', sites: ['UK'], UK: { copies: 2, median: 85, lowest: 70, checked: '2026-10-14T10:00Z' } } },
            editions: { PAL: { 'Resident Evil 4 Limited Edition': 'Resident Evil 4 Limited Edition' }, US: {} } }, null)`);
        // ticked as US, but it is a PAL edition: valued on eBay UK
        assert.deepEqual(Array.from(run(`collectionValue({ title: 'Resident Evil 4 Limited Edition', region: 'US', condition: 'complete', qty: 1, paid: null })`)), [85, 'GBP', 'ebay']);
        assert.equal(run(`collectionValue({ title: 'Resident Evil 4 Premium Edition', region: 'US', condition: 'loose', qty: 1, paid: null })[2]`), 'none', 'not priced yet: no value, never the plain game\'s');
        el('collectionGame').value = 'x';
        run(`collectionSuggestions = ['Resident Evil 4 Limited Edition']; pickCollectionSuggestion(0)`);
        assert.equal(el('collectionRegion').value, 'PAL', 'picking a PAL edition ticks PAL');
    } finally {
        run(`editionsData = null`);
        run(`setLibrary(${saved})`);
        run(`setPrices(null, null)`);
    }
});

await check('editions: covers use the edition\'s own box when Libretro has one, otherwise the game\'s box in the edition\'s region', async () => {
    const run = (code) => vm.runInContext(code, context);
    run(`editionsData = ${JSON.stringify(JSON.parse(read('editions.json')))}`);
    run(`coversShown = true; coverIndex = { 'resident evil 4': ['Resident Evil 4', ' (USA)', ' (Europe) (En,Fr,De,Es,It)'], 'mortal kombat armageddon': ['Mortal Kombat - Armageddon', ' (USA)', ''] }`);
    try {
        const base = 'https://thumbnails.libretro.com/Sony%20-%20PlayStation%202/Named_Boxarts/';
        assert.equal(run(`coverUrl('Resident Evil 4 Limited Edition', 'US')`), base + encodeURIComponent('Resident Evil 4 (Europe) (En,Fr,De,Es,It)') + '.png', 'the PAL steelbook gets the Europe box, whatever region is asked');
        assert.equal(run(`coverUrl('Resident Evil 4 Premium Edition', 'PAL')`), base + encodeURIComponent('Resident Evil 4 (USA)') + '.png');
        assert.equal(run(`coverUrl('Mortal Kombat: Armageddon Premium Edition', 'US')`), base + encodeURIComponent('Mortal Kombat - Armageddon (USA) (Premium Edition)') + '.png', 'its own file when the entry names one');
        assert.equal(run(`coverUrl('Driver 2 Limited Edition', 'PAL')`), '', 'no game page, no cover');
        assert.match(run(`coverUrl('Resident Evil 4', 'US')`), /Resident%20Evil%204%20\(USA\)/, 'the plain game is unchanged');
        run(`editionsData = { lists: { PAL: [{ title: 'Kuon Limited Edition', game: 'Kuon', cover: '../x' }] } }`);
        assert.equal(run(`coverUrl('Kuon Limited Edition', 'PAL')`), '', 'a file name with a slash is not used');
    } finally {
        run(`editionsData = null; coverIndex = null; coverIndexState = 'idle'`);
    }
});

await check('Gacha: four machines of twenty capsules, free coins, prizes kept under My collection', async () => {
    const run = (code) => vm.runInContext(code, context);
    const file = JSON.parse(read('gacha.json'));
    const kept = new Map();
    context.localStorage = { getItem: (key) => (kept.has(key) ? kept.get(key) : null), setItem: (key, value) => { kept.set(key, String(value)); } };
    // The file: four machines, 20 capsules each as 5 commons x3, 1 uncommon x4 and 1 super rare x1; every game is in the library.
    assert.deepEqual(file.machines.map(m => m.id), ['horror', 'action', 'open_world', 'rpg']);
    const library = new Set([...JSON.parse(read('data/ps2_database.json')), ...JSON.parse(read('search_extra_titles.json')).titles,
        ...Object.values(JSON.parse(read('editions.json')).lists).flat().map(entry => entry.title)]);
    for (const machine of file.machines) {
        const by = (tier) => machine.prizes.filter(prize => prize.tier === tier);
        assert.equal(machine.prizes.reduce((sum, prize) => sum + prize.qty, 0), 20, `${machine.id}: 20 capsules`);
        assert.deepEqual([by('common').length, by('uncommon').length, by('super_rare').length], [5, 1, 1], machine.id);
        assert.ok(by('common').every(prize => prize.qty === 3) && by('uncommon')[0].qty === 4 && by('super_rare')[0].qty === 1, machine.id);
        for (const prize of machine.prizes) assert.ok(library.has(prize.title), `${prize.title} is a library game`);
    }
    assert.equal(new Set(file.machines.flatMap(m => m.prizes.map(prize => prize.title))).size, 28, 'no game in two machines');
    // A file that is wrong in places still draws what is right.
    assert.equal(run(`cleanGachaData({ machines: 'x' })`), null);
    assert.deepEqual(evalJson(`cleanGachaData({ daily_coins: 99, machines: [{ id: 'A b', name: 'x', prizes: [] }, { id: 'ok', name: 'Ok', prizes: [{ title: 'Kuon', tier: 'super_rare', qty: 1 }, { title: 'Kuon', tier: 'common', qty: 1 }, { title: '<b>', tier: 'mythic', qty: 1 }, { title: 'Siren', tier: 'common', qty: 0 }] }] })`),
        { dailyCoins: 10, machines: [{ id: 'ok', name: 'Ok', tagline: '', prizes: [{ title: 'Kuon', tier: 'super_rare', qty: 1 }] }] });

    // Turning: coins, drawing without replacement, restocking.
    context.__gacha = file;
    run(`gachaData = cleanGachaData(__gacha); gachaFileState = 'ready'; gachaMachineId = 'horror'; gachaSaved = cleanGachaSaved({}); gachaShown = null; gachaTurning = false`);
    const day = new Date(2026, 9, 15, 10, 0, 0);
    context.__day = day;
    assert.equal(run(`gachaToday(__day)`), '2026-10-15');
    assert.equal(run(`gachaCoinsNow(__day)`), 3, 'three free coins a day');
    let rolls = 0;
    context.__rng = () => [0.999, 0, 0.5][rolls++ % 3];
    const first = evalJson(`gachaPull('horror', __rng, __day)`);
    assert.equal(first.title, 'Rule of Rose', 'the last capsule in the list is picked at the top of the range');
    assert.equal(first.tier, 'super_rare');
    const second = evalJson(`gachaPull('horror', __rng, __day)`);
    assert.equal(second.title, 'Resident Evil 4', 'the first at the bottom');
    const third = evalJson(`gachaPull('horror', __rng, __day)`);
    assert.equal(run(`gachaSaved.coins`), 0);
    assert.equal(run(`gachaPull('horror', __rng, __day)`), null, 'no coin, no capsule');
    assert.equal(run(`gachaStock(gachaMachineOf('horror'))['Rule of Rose']`), 0, 'a capsule taken is gone');
    assert.equal(run(`gachaTotal(gachaStock(gachaMachineOf('horror')))`), 17);
    assert.equal(run(`gachaSaved.prizes.length`), 3);
    assert.ok([...kept.keys()].includes('ps2-sentiment-tracker.gacha'), 'kept in this browser');
    assert.ok(JSON.parse(kept.get('ps2-sentiment-tracker.gacha')).left.horror, 'the machine\'s place is kept');
    // The next day brings coins back, and a machine emptied one capsule at a time fills up again with every game drawn exactly its count.
    context.__next = new Date(2026, 9, 16, 9, 0, 0);
    const drawn = {};
    let restocked = 0;
    for (let i = 0; i < 17; i++) {
        if (i % 3 === 0) { context.__next = new Date(2026, 9, 16 + i / 3, 9, 0, 0); }
        const pull = evalJson(`gachaPull('horror', Math.random, __next)`);
        assert.ok(pull, `pull ${i}`);
        drawn[pull.title] = (drawn[pull.title] || 0) + 1;
        if (pull.restocked) restocked++;
    }
    assert.equal(restocked, 1, 'the machine is filled again when its last capsule is out');
    assert.equal(run(`gachaTotal(gachaStock(gachaMachineOf('horror')))`), 20);
    const everyDraw = run(`gachaSaved.prizes`).length;
    assert.equal(everyDraw, 20);
    const counts = {};
    for (const prize of evalJson(`gachaSaved.prizes`)) counts[prize.title] = (counts[prize.title] || 0) + 1;
    for (const prize of file.machines[0].prizes) assert.equal(counts[prize.title], prize.qty, `${prize.title}: exactly its count came out of twenty`);
    // Saved state is cleaned: nothing in it can add a game or more capsules than the file stocks.
    run(`gachaSaved = cleanGachaSaved({ day: 'x', coins: 99, left: { horror: { 'Rule of Rose': 7, 'Not a game': 2 } }, prizes: [{ title: 'Kuon', tier: 'super_rare' }, { title: 'x', tier: 'bogus' }] })`);
    assert.equal(run(`gachaSaved.coins`), 10);
    assert.equal(run(`gachaSaved.prizes.length`), 1);
    assert.equal(run(`gachaStock(gachaMachineOf('horror'))['Rule of Rose']`), 1, 'never more than the machine holds');
    assert.equal(run(`'Not a game' in gachaStock(gachaMachineOf('horror'))`), false);

    // The page: coins, odds, the capsule that came out, and the prizes tab inside My collection.
    run(`gachaSaved = cleanGachaSaved({}); gachaShown = null; coversShown = false; setPrices(${JSON.stringify({ games: { 'Siren': { US: { copies: 44, lowest: 60, median: 71.91 } } } })}, null)`);
    run(`renderGacha('en-GB')`);
    assert.match(el('gachaCoins').innerHTML, /3 of 3 coins left today/);
    assert.match(el('gachaOdds').innerHTML, /15 of 15[\s\S]*75%|15 of 15/);
    assert.equal(el('gachaTurn').disabled, false);
    assert.equal((el('gachaContents').innerHTML.match(/<li /g) || []).length, 7);
    assert.match(el('gachaContents').innerHTML, /\$71\.91 median|\$72 median/, 'a game with a price shows it');
    assert.match(el('gachaContents').innerHTML, /no eBay price yet/, 'a game without one says so');
    assert.doesNotMatch(el('gachaMachines').innerHTML + el('gachaContents').innerHTML, /<script|<img/);
    context.__rng2 = () => 0.5;
    const turned = evalJson(`gachaPull('horror', __rng2, new Date())`);
    run(`gachaShown = ${JSON.stringify(turned)}; renderGacha('en-GB')`);
    assert.match(el('gachaResult').innerHTML, new RegExp(`gacha-prize tier-${turned.tier}`));
    assert.match(el('gachaResult').innerHTML, /My gacha prizes/);
    run(`showView('collection')`);
    assert.equal(el('tabCollection').classList.contains('is-active'), true);
    run(`showCollectionTab('prizes')`);
    assert.equal(el('prizesSection').classList.contains('hidden'), false);
    assert.equal(el('collectionSection').classList.contains('hidden'), true);
    assert.equal(el('collTabPrizes').attributes['aria-selected'], 'true');
    assert.match(el('prizesSummary').textContent, /1 capsule opened/);
    assert.equal((el('prizesList').innerHTML.match(/<li /g) || []).length, 1);
    assert.match(el('collTabPrizesCount').textContent, /1/);
    assert.equal(el('collTabPrizesCount').classList.contains('hidden'), false);
    run(`showCollectionTab('games')`);
    assert.equal(el('collectionSection').classList.contains('hidden'), false);
    assert.equal(el('prizesSection').classList.contains('hidden'), true);
    context.confirm = () => true;
    run(`clearPrizes()`);
    assert.match(el('prizesSummary').textContent, /Nothing here yet/);
    // The Gacha page is switched off (GACHA_SHOWN): no tab, and #gacha falls back to the Tracker.
    assert.match(read('index.html'), /id="tabGacha"[^>]*class="view-tab hidden"/, 'the Gacha tab is hidden');
    assert.match(read('index.html'), /id="collTabPrizes"[^>]*class="view-tab hidden"/, 'so is My gacha prizes');
    assert.match(read('retro.css'), /body \.view-tab\.hidden \{ display: none; \}/, 'and the stylesheet lets .hidden win over .view-tab');
    assert.equal(run(`isView('gacha')`), false, '#gacha does not open the page while it is off');
    run(`showView('gacha')`);
    assert.equal(el('viewGacha').classList.contains('hidden'), true);
    assert.equal(el('viewDashboard').classList.contains('hidden'), false);
    // Underrated: the file, the daily pick (random, the same all day, no repeat within a round) and the page.
    {
        const raw = JSON.parse(read('underrated.json'));
        const database = JSON.parse(read('data/ps2_database.json'));
        const library = new Set([...(Array.isArray(database) ? database : database.games || []).map(g => typeof g === 'string' ? g : g.title || g.name), ...JSON.parse(read('search_extra_titles.json')).titles].map(t => String(t).toLowerCase()));
        assert.equal(raw.games.length, 100, 'a hundred games');
        assert.equal(raw.games[0].title, 'Rygar: The Legendary Adventure', 'Rygar is the game of the launch day');
        assert.match(raw.launch, /^2026-10-15$/);
        assert.ok(raw.games.filter(g => g.developer).length >= 90, 'a developer for nearly every game');
        assert.equal(raw.games[0].developer, 'Tecmo');
        const titles = raw.games.map(g => g.title);
        assert.equal(new Set(titles.map(t => t.toLowerCase())).size, titles.length, 'no game twice');
        for (const t of titles) assert.ok(library.has(t.toLowerCase()), `${t} is a library name`);
        for (const g of raw.games) assert.ok(g.why && g.genre && (g.year === null || Number.isInteger(g.year)), `${g.title} has a reason, a genre and a year or null`);
        const never = new Set(raw.never.map(t => t.toLowerCase()));
        for (const t of titles) assert.ok(!never.has(t.toLowerCase()), `${t} is on the never list`);
        for (const must of ['Okami', 'Grand Theft Auto: San Andreas', 'Medal of Honor: Frontline']) assert.ok(never.has(must.toLowerCase()), `${must} is kept off`);
        assert.ok(Object.values(raw.lists).every(l => /^https:\/\//.test(l.url)), 'every list has a link');
        assert.ok(!JSON.stringify(raw).match(/"rank"|"score"/), 'no invented ranks or scores');
        const n = raw.games.length;
        const launchDay = Math.floor(Date.parse(raw.launch + 'T00:00:00Z') / 86400000);
        const pickOn = (day) => evalJson(`underratedPickFor(${n}, ${launchDay}, ${day})`);
        assert.equal(pickOn(launchDay), 0, 'launch day: Rygar');
        assert.deepEqual(Array.from({ length: n }, (_, i) => pickOn(launchDay + i)), Array.from({ length: n }, (_, i) => i), 'one new game a day in file order');
        assert.equal(evalJson(`underratedRevealed(${n}, ${launchDay}, ${launchDay})`), 1, 'one game on show on day one');
        assert.equal(evalJson(`underratedRevealed(${n}, ${launchDay}, ${launchDay + 9})`), 10);
        assert.equal(evalJson(`underratedRevealed(${n}, ${launchDay}, ${launchDay + 500})`), n, 'all of them after the last day');
        const round1 = Array.from({ length: n }, (_, i) => pickOn(launchDay + n + i));
        assert.equal(new Set(round1).size, n, 'no repeat inside the next round');
        assert.notDeepEqual(round1, Array.from({ length: n }, (_, i) => i), 'the next round is shuffled');
        assert.deepEqual(pickOn(launchDay + n + 3), pickOn(launchDay + n + 3), 'the same day gives the same game');
        const pickNow = Date.now();
        run(`underratedData = cleanUnderratedData(${JSON.stringify(raw)}); underratedFileState = 'ready'; underratedFilter = 'all'`);
        const dayStamp = (day) => (day * 86400000) + 43200000;
        run(`renderUnderrated(${dayStamp(launchDay)})`);
        assert.equal((el('underratedGrid').innerHTML.match(/<li /g) || []).length, 1, 'only today\'s game on the launch day');
        assert.match(el('underratedToday').innerHTML, /Rygar/);
        assert.match(el('underratedDays').innerHTML, /from tomorrow/, 'no earlier days yet');
        run(`renderUnderrated(${dayStamp(launchDay + 3)})`);
        assert.equal((el('underratedGrid').innerHTML.match(/<li /g) || []).length, 4, 'one more game each day');
        assert.equal((el('underratedDays').innerHTML.match(/<li /g) || []).length, 3, 'only days since launch');
        run(`renderUnderrated(${dayStamp(launchDay + 20)})`);
        run(`showView('underrated', false)`);
        run(`renderUnderrated(${dayStamp(launchDay + 20)})`);
        assert.equal(el('viewUnderrated').classList.contains('hidden'), false);
        assert.equal(el('tabUnderrated').classList.contains('is-active'), true);
        assert.equal(run(`isView('underrated')`), true, '#underrated opens the page');
        assert.match(el('underratedToday').innerHTML, /Game of the day/);
        assert.match(el('underratedToday').innerHTML, /under-attn/, 'the game of the day shows its attention bar');
        assert.match(el('underratedToday').innerHTML, /Not named in the last 14 days|Named \d+ /, 'it says how often the feed named it');
        assert.match(el('underratedToday').innerHTML, /metacritic\.com\/search\//, 'a link to find reviews');
        assert.ok(!/\b\d\/10\b|metascore/i.test(el('underratedToday').innerHTML), 'no review score is invented');
        run(`visibleFeedData = [{ games: ['Rygar: The Legendary Adventure'], matched_games: ['Rygar: The Legendary Adventure'], game: 'Rygar: The Legendary Adventure', timestamp: '2026-10-14 10:00:00 UTC' }, { games: ['Other Game'], matched_games: ['Other Game'], game: 'Other Game', timestamp: '2026-10-14 10:00:00 UTC' }]; underratedMentionCache = null`);
        assert.equal(evalJson(`underratedMentionInfo('Rygar: The Legendary Adventure').n`), 1, 'one item names it');
        assert.equal(evalJson(`underratedMentionInfo('Rygar: The Legendary Adventure').rank`), 1);
        assert.equal(evalJson(`underratedMentionInfo('Never Named').rank`), null);
        run(`visibleFeedData = []; underratedMentionCache = null`);
        assert.equal((el('underratedDays').innerHTML.match(/<li /g) || []).length, 7, 'seven earlier days');
        assert.equal((el('underratedGrid').innerHTML.match(/<li /g) || []).length, 21, 'the games revealed so far');
        run(`underratedFilter = 'g:' + underratedData.games[0].genre; renderUnderrated(${dayStamp(launchDay + 20)})`);
        const inGenre = raw.games.slice(0, 21).filter(g => g.genre === raw.games[0].genre).length;
        assert.equal((el('underratedGrid').innerHTML.match(/<li /g) || []).length, inGenre, 'a genre chip narrows the grid');
        run(`underratedFilter = 'all'; renderUnderrated(${dayStamp(launchDay + 20)})`);
        assert.match(el('underratedNote').innerHTML, /denofgeek\.com/, 'the lists are credited with links');
        assert.equal(run(`cleanUnderratedData({games: [{title: 'A', why: 'x'}, {title: 'a', why: 'y'}, {title: 5}]}).games.length`), 1, 'bad rows and repeats are dropped');
        assert.equal(run(`cleanUnderratedData({})`), null);
        run(`showView('dashboard', false)`);
    }
    // The console: drawn once, one lit square per capsule left, and a coin plays the whole sequence (tray out, disc, prize).
    run(`gachaSaved = cleanGachaSaved({}); gachaShown = null; gachaTurning = false; gachaMachineId = 'horror'; renderGacha('en-GB')`);
    assert.match(el('gachaMachine').innerHTML, /id="gxPips"/);
    assert.equal(el('gachaMachine').dataset.built, '1');
    assert.equal((el('gxPips').innerHTML.match(/class="gx-pip is-lit"/g) || []).length, 20, 'a full machine lights twenty squares');
    const svgBefore = el('gachaMachine').innerHTML;
    context.window.matchMedia = () => ({ matches: true });   // no waiting in the test
    context.localStorage = { getItem: (key) => (kept.has(key) ? kept.get(key) : null), setItem: (key, value) => { kept.set(key, String(value)); } };
    await vm.runInContext(`gachaTurn()`, context);
    assert.equal(el('gachaMachine').classList.contains('out'), true, 'the tray is out with the disc');
    assert.equal(el('gachaMachine').classList.contains('pop'), true);
    assert.equal(run(`gachaTurning`), false);
    assert.equal(el('gachaMachine').innerHTML, svgBefore, 'the machine is not redrawn during a turn, so its animation is not cut');
    assert.equal((el('gxPips').innerHTML.match(/class="gx-pip is-lit"/g) || []).length, 19, 'one square goes dark');
    assert.match(el('gachaMachine').classList.contains('tier-common') || el('gachaMachine').classList.contains('tier-uncommon') || el('gachaMachine').classList.contains('tier-super_rare') ? 'tier' : '', /tier/, 'the disc wears the prize\'s rarity colour');
    assert.match(el('gachaResult').innerHTML, /gacha-prize/);
    // The next coin closes the tray first.
    await vm.runInContext(`gachaTurn()`, context);
    assert.equal((el('gxPips').innerHTML.match(/class="gx-pip is-lit"/g) || []).length, 18);
    run(`gachaPick('rpg')`);
    for (const state of ['on', 'out', 'pop']) assert.equal(el('gachaMachine').classList.contains(state), false, `switching machine puts the console to rest (${state})`);
    assert.equal(run(`gachaSaved.coins`), 1, 'three coins, two spent');
    run(`gachaSaved.coins = 0`);
    await vm.runInContext(`gachaTurn()`, context);
    assert.match(el('gachaResult').innerHTML, /No coins left today/);
    const css = read('retro.css');
    assert.match(css, /prefers-reduced-motion: reduce\) \{[^@]*gx-sweep/, 'the animation is switched off for those who ask');
    assert.match(read('index.html'), /id="gxText"/);
    // Small covers: a thumbnail in each row of the contents, small tiles for the prizes.
    assert.equal((el('gachaContents').innerHTML.match(/class="coll-cover gacha-thumb"/g) || []).length, 7);
    assert.match(css, /body \.prize-grid \{ grid-template-columns: repeat\(auto-fill, 5\.5rem\); \}/);
    // A browser that will not store anything still plays.
    context.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
    run(`loadGachaState(); gachaSaved = cleanGachaSaved({}); gachaCoinsNow(new Date())`);
    assert.ok(run(`gachaPull('rpg', Math.random, new Date())`), 'a turn works without storage');
    assert.equal(run(`gachaKept`), false);
    run(`renderGacha('en-GB')`);
    assert.match(el('gachaNote').textContent, /would not store your progress/);
    // Nothing is sold or sent: no network call from a turn.
    const asked = [];
    const real = context.fetch;
    context.fetch = async (url) => { asked.push(String(url)); return real(url); };
    run(`gachaPull('rpg', Math.random, new Date())`);
    context.fetch = real;
    assert.deepEqual(asked, []);
    run(`gachaData = null; gachaFileState = 'idle'; gachaMachineId = ''; gachaSaved = cleanGachaSaved({}); showView('dashboard')`);
});

await check('shop buttons: each shop has its own look, and the colours are tokens', () => {
    const run = (code) => vm.runInContext(code, context);
    const chips = run(`priceLookupHtml('Haunting Ground')`);
    assert.equal((chips.match(/class="price-link price-link--pc"/g) || []).length, 2, 'Price Charting, PAL and US');
    assert.equal((chips.match(/class="price-link price-link--ebay"/g) || []).length, 6, 'eBay UK, DE, FR, IT, ES, US');
    assert.equal((chips.match(/class="price-link price-link--cex"/g) || []).length, 1);
    assert.equal((chips.match(/<span class="ebay-wordmark" aria-hidden="true">/g) || []).length, 6);
    for (const code of ['UK', 'DE', 'FR', 'IT', 'ES', 'US']) assert.match(chips, new RegExp(`<span class="price-sup">${code}</span>`));
    assert.equal((chips.match(/aria-label="[^"]+"/g) || []).length, 10, 'every button, and the row, keeps its spoken name');
    const css = read('retro.css');
    for (const rule of ['body .price-link--pc', 'body .price-link--ebay', 'body .price-link--cex', 'body .brand-btn-how', 'body .brand-btn-sources', 'body .brand-btn-currency']) {
        assert.ok(css.includes(rule), rule);
    }
    const page = read('index.html');
    assert.match(page, /class="brand-btn brand-btn-how"/);
    assert.match(page, /class="brand-btn brand-btn-sources"/);
    assert.match(page, /Plus\+Jakarta\+Sans/);
});

console.log(`dashboard checks passed (${passed})`);
