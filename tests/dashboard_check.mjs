// Offline checks for the dashboard's inline script in index.html (run by tests/test_scraper.py).
//   node tests/dashboard_check.mjs                  runs the checks below
//   node tests/dashboard_check.mjs --validate FILE  prints validateConfig() verdicts for the configs in FILE
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
    location: { hostname: 'localhost', pathname: '/' },
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
            : src.type === 'reddit' ? `reddit:${src.subreddit.toLowerCase()}` : src.url;
        assert.equal(keys[i], expected);
    });
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
    for (const tab of ['news', 'reddit', 'youtube', 'podcast']) {
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

console.log(`dashboard checks passed (${passed})`);
```[cite: 1]
