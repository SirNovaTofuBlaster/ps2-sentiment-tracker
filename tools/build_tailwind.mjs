// Builds tailwind.css, the stylesheet index.html and guide.html load instead of Tailwind's Play CDN script
// (cdn.tailwindcss.com, which builds the same CSS in every visitor's browser on every load).
//
// How: it opens each page in headless Chromium with Tailwind's own Play CDN build (3.4.17, the version the
// site used) and the page's own `tailwind.config`, lets it generate CSS for what the page contains, and
// keeps the generated <style>. So the result is what the CDN would have made. Nothing is sent anywhere:
// the Play script is a local file you give it, and the pages are served from a temporary local server.
//
//   npm i playwright                      (once; any Chromium that Playwright can launch)
//   curl -o /tmp/tailwind-play-3.4.17.js https://cdn.tailwindcss.com/3.4.17
//   node tools/build_tailwind.mjs /tmp/tailwind-play-3.4.17.js
//
// Re-run it whenever a page gets a Tailwind class it did not have (tests/test_tailwind_css.py fails then).
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(process.env.PLAYWRIGHT_FROM || import.meta.url);
const { chromium } = require('playwright');

const play = process.argv[2];
if (!play || !fs.existsSync(play)) { console.error('usage: node tools/build_tailwind.mjs <tailwind play cdn 3.4.17 .js file>'); process.exit(2); }
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
// Each page's own Tailwind settings, exactly as it had them in its `tailwind.config` before the CDN was dropped.
const PAGES = {
  'index.html': { out: 'tailwind.css', config: {
    darkMode: 'class',
    theme: { extend: {
      colors: { ps2neon: '#4FA8E8', ps2dark: '#0A0A0C', ps2card: '#16161B', ps2border: '#27272E',
        spindle: { red: '#E5303A', yellow: '#F5C52E', blue: '#2F9BE0', teal: '#2DBFA6' } },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'], serif: ['Playfair Display', 'Georgia', 'serif'], mono: ['JetBrains Mono', 'monospace'] },
    } } } },
  'guide.html': { out: 'tailwind-guide.css', config: {
    darkMode: 'class',
    theme: { extend: { colors: { ps2dark: '#0A0A0C', ps2card: '#16161B', ps2border: '#27272E' } } } } },
};
const TYPES = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json' };

const server = http.createServer((req, res) => {
  const file = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
  res.end(fs.readFileSync(file));
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch();
for (const [page, { out, config }] of Object.entries(PAGES)) {
  const p = await browser.newPage();
  // The page no longer loads the Play script or sets a config: this build supplies both.
  await p.route('**/cdn.tailwindcss.com/**', r => r.fulfill({ contentType: 'application/javascript', body: `${fs.readFileSync(play, 'utf8')}\n;tailwind.config = ${JSON.stringify(config)};` }));
  await p.route(/fonts\.googleapis|fonts\.gstatic|cdnjs|jsdelivr|libretro|thumbnails/, r => r.abort());
  let html = fs.readFileSync(path.join(root, page), 'utf8');
  html = html.replace(/\s*<link rel="stylesheet" href="tailwind[\w-]*\.css[^"]*">/, '').replace('<head>', '<head><script src="https://cdn.tailwindcss.com/3.4.17"></script>');
  await p.route(`http://localhost:${port}/__build.html`, r => r.fulfill({ contentType: 'text/html', body: html }));
  await p.goto(`http://localhost:${port}/__build.html`, { waitUntil: 'load' });
  await p.waitForTimeout(1500);
  // The Play script styles only what is in the page at that moment, so a class that sits in a script's template
  // (drawn later, or only in some state) would be missed. Every word in the page's source is offered to it as a
  // class on a hidden element; Tailwind ignores the words that are not utilities. The stylesheet is therefore a
  // superset of what the CDN made for a visitor: the same rules for the same classes, whenever they appear.
  const words = [...new Set(html.match(/[A-Za-z0-9_:\-\/\[\]\.%#,()]{2,60}/g) || [])].filter(w => /[a-z]/.test(w));
  await p.evaluate(list => { const d = document.createElement('div'); d.hidden = true; d.className = list.join(' '); document.body.appendChild(d); }, words);
  await p.waitForTimeout(2500);
  const css = await p.evaluate(() => [...document.querySelectorAll('style')].filter(s => /tailwindcss v3/.test(s.textContent)).map(s => s.textContent).join('\n'));
  if (!css) throw new Error(`no Tailwind CSS was generated for ${page}`);
  const rules = css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\s+/g, ' ').trim();
  fs.writeFileSync(path.join(root, out), `/* Built by tools/build_tailwind.mjs from Tailwind 3.4.17; do not edit by hand. */\n${rules}\n`);
  console.log(`${out}: ${rules.length} bytes`);
  await p.close();
}
await browser.close();
server.close();
