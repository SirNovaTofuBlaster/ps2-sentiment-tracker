<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#0C1120">
    <title>How to Use Spindle</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: { extend: { colors: {
                ps2dark: '#0B0F1A',
                ps2card: '#121826',
                ps2border: '#232C42',
            } } }
        }
    </script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="retro.css">
    <style>
        kbd { font-size: 0.75rem; padding: 0.1rem 0.35rem; border: 1px solid #475569; }
        section { scroll-margin-top: 5rem; }
    </style>
</head>
<body class="bg-ps2dark min-h-screen">

        <header class="brand-bar">
        <div class="max-w-3xl mx-auto px-4 h-16 flex items-center justify-between gap-3">
            <div class="flex items-center gap-3 min-w-0">
                <svg width="32" height="32" viewBox="0 0 56 56" aria-hidden="true" class="shrink-0">
                    <circle cx="28" cy="28" r="26" fill="none" stroke="#4C8DFF" stroke-width="3"></circle>
                    <circle cx="28" cy="28" r="7" fill="none" stroke="#4C8DFF" stroke-width="3"></circle>
                </svg>
                <div class="min-w-0">
                    <h1 class="truncate">How to use Spindle</h1>
                    <p class="text-xs text-slate-400 truncate">Sources, weights and saving, step by step</p>
                </div>
            </div>
            <a href="index.html#sourcesSection" class="shrink-0 from-blue-600 text-xs px-3 py-2 flex items-center gap-2">
                <i class="fa-solid fa-arrow-left"></i> Dashboard
            </a>
        </div>
    </header>

    <main class="max-w-3xl mx-auto px-4 py-8 space-y-10 text-sm leading-relaxed text-slate-300">

        <nav aria-label="Contents" class="bg-ps2card p-5">
            <h2 class="mb-2">On this page</h2>
            <ol class="list-decimal pl-5 grid sm:grid-cols-2 gap-x-6 gap-y-1 text-cyan-400 steps">
                <li><a class="hover:underline" href="#overview">What the dashboard shows</a></li>
                <li><a class="hover:underline" href="#prices">The price links</a></li>
                <li><a class="hover:underline" href="#demand">The Demand Index</a></li>
                <li><a class="hover:underline" href="#sources">The Sources &amp; Weights panel</a></li>
                <li><a class="hover:underline" href="#add">Add a source</a></li>
                <li><a class="hover:underline" href="#weights">Weights</a></li>
                <li><a class="hover:underline" href="#save">Save your changes</a></li>
                <li><a class="hover:underline" href="#token">One-click saving with a token</a></li>
                <li><a class="hover:underline" href="#status">What the status badges mean</a></li>
                <li><a class="hover:underline" href="#problems">If something looks wrong</a></li>
                <li><a class="hover:underline" href="#faq">Questions</a></li>
            </ol>
        </nav>

        <section id="overview" class="space-y-3">
            <h2>1. What the dashboard shows</h2>
            <p>Every hour a robot on GitHub reads gaming news sites, Reddit, YouTube channels and podcasts. For every headline, video and episode it checks whether a PlayStation 2 game is mentioned, whether it sounds like remaster or remake news, and how positive the wording is. The dashboard shows the result:</p>
            <ul class="list-disc pl-5 space-y-1">
                <li><b class="text-white">The four numbers at the top</b>: how many items were collected, how many look like remaster news, how many sources are switched on, and the overall mood from 0 to 100.</li>
                <li><b class="text-white">Most Mentioned Games</b>: the fifteen PS2 games mentioned most often, with each one's mention count and share of all game mentions. It recalculates whenever the feed loads or you switch a source on or off.</li>
                <li><b class="text-white">The table</b>: everything that was collected. Use the search box and the menus to show only remaster news, only matched PS2 games, or one kind of source.</li>
                <li><b class="text-white">On a phone</b>: the table becomes a list of cards, 25 to a page, and each game's price links sit on one line that you swipe sideways.</li>
            </ul>
            <p><b class="text-white">Times are shown in your own time zone.</b> The robot works in UTC, so "Last sync" and the times in the table are converted to wherever you are. Hover over a time to see the original.</p>
            <p><b class="text-white">About the mood score.</b> It reads the wording of a headline, not what the headline is about. Words like "masterpiece" or "underrated" push it up, "broken" or "disappointing" push it down, and "not a masterpiece" counts as criticism rather than praise. Announcements are deliberately neutral: a remaster being announced is news, not good news, so words like "remaster" and "announced" no longer raise the score. It is a rough guide to tone and nothing more.</p>
            <p><b class="text-white">About the remaster flag.</b> Clear wording — remaster, remake, reboot, director's cut — flags on its own. Everyday words like "collection", "ports" or "returns" only flag when a PS2 game was also recognised in the same headline, because "my PS2 collection" isn't news.</p>
        </section>

        <section id="prices" class="space-y-3">
            <h2>2. The price links</h2>
            <p>Every recognised game carries a row of small amber buttons, split into <b class="text-white">PAL</b> (Europe) and <b class="text-white">US</b>. They are <b class="text-white">searches, not prices</b>: nothing is stored here and no number is shown on this page. Clicking one opens that shop or price guide with the game already searched for.</p>
            <ul class="list-disc pl-5 space-y-1">
                <li><b class="text-white">Price Charting</b> tracks what copies have actually sold for, which is the closest thing to a market value. There is a separate PAL and US price for most games, and they can differ a lot.</li>
                <li><b class="text-white">eBay</b> shows what sellers are <i>asking</i> today, not what anything sold for. Asking prices usually sit well above real ones, and a single graded or sealed copy can make a game look far more expensive than it is.</li>
                <li><b class="text-white">CeX</b> is one shop's own price in the UK. It's a real "what would this cost me this afternoon" figure, but it only covers games CeX still trades and it moves with their stock rather than with the market.</li>
            </ul>
            <p>Because these are searches, you may land on the wrong edition or a game with a similar name — always check the result matches the game and the region before trusting a number.</p>
        </section>

        <section id="demand" class="space-y-3">
            <h2>3. The Demand Index</h2>
            <p>This section only appears once the daily job has run; if you don't see it, nothing is wrong. It asks a different question from Most Mentioned Games: not "what is being talked about here" but "what are people looking up".</p>
            <p>It counts how often each game's Wikipedia article was read over the last four weeks and blends that with how often the game is mentioned in this feed. The <b class="text-white">arrow and percentage</b> are the interesting part: they compare the last seven days against the seven before, so a game climbing sharply shows up even if a famous game has more readers overall.</p>
            <p class="text-slate-400">It updates once a day, because Wikipedia only publishes its reading figures daily. A game that appears with no percentage simply hasn't enough history yet.</p>
        </section>

        <section id="sources" class="space-y-3">
            <h2>4. The Sources &amp; Weights panel</h2>
            <p>Click <b class="text-white"><i class="fa-solid fa-sliders"></i> Sources</b> at the top of the dashboard. There is one tab per kind of source (News sites, Reddit, YouTube, Podcasts) and a <b class="text-white">Weights &amp; schedule</b> tab.</p>
            <ul class="list-disc pl-5 space-y-1">
                <li><b class="text-white">Switch a source on or off</b> with the checkbox at the start of its row. Its items disappear from the dashboard straight away. Nothing is deleted: switch it back on whenever you like.</li>
                <li><b class="text-white">Find a source</b> with the search box, or sort the list, e.g. YouTube by subscribers or total views and podcasts by Apple ratings or chart position.</li>
                <li>The numbers (subscribers, views, ratings) were measured on the date shown at the top of the panel. The <b class="text-white">Status</b> column is live.</li>
                <li><b class="text-white">On a phone</b> the tabs are on one line that swipes sideways, each source is a card, and the list scrolls inside its own box so the form for adding a source stays close by.</li>
                <li>A changed list shows an <b class="text-white">Unsaved changes</b> badge. Your changes only affect your screen until you <a class="text-cyan-400 hover:underline" href="#save">save them</a>. <b class="text-white">Discard</b> undoes everything since the last save.</li>
            </ul>
        </section>

        <section id="add" class="space-y-4">
            <h2>5. Add a source</h2>
            <p>Open the tab for the kind of source, paste the link into the box under the list and press <b class="text-white">Add source</b>. The name is filled in for you where possible. <b class="text-white">Group</b> only sorts the list, and <b class="text-white">Role</b> sets its <a class="text-cyan-400 hover:underline" href="#weights">weight</a>.</p>
            <div class="grid gap-4 sm:grid-cols-2">
                <div class="bg-ps2card p-4">
                    <h3 class="mb-1"><i class="fa-brands fa-youtube"></i> YouTube channel</h3>
                    <p>Open the channel on YouTube and copy the address from the address bar, e.g. <span class="font-mono-custom text-cyan-300">https://www.youtube.com/@IGN</span>. Video links don't work. The robot looks the channel up on its next run; if it can't, the status says so (see <a class="text-cyan-400 hover:underline" href="#problems">below</a>).</p>
                </div>
                <div class="bg-ps2card p-4">
                    <h3 class="mb-1"><i class="fa-solid fa-podcast"></i> Podcast</h3>
                    <p>Find the show on <a class="text-cyan-400 hover:underline" href="https://podcasts.apple.com" target="_blank" rel="noopener noreferrer">Apple Podcasts</a> and paste its link, e.g. <span class="font-mono-custom text-cyan-300">https://podcasts.apple.com/us/podcast/retronauts/id672857593</span>. The name and feed are filled in automatically. Spotify links can't be used because Spotify doesn't publish feeds.</p>
                </div>
                <div class="bg-ps2card p-4">
                    <h3 class="mb-1"><i class="fa-solid fa-newspaper"></i> News site</h3>
                    <p>Paste the site's RSS feed link. Many sites have one at their address followed by <span class="font-mono-custom text-cyan-300">/feed</span> or <span class="font-mono-custom text-cyan-300">/rss</span>; otherwise look for an RSS icon. Give it a name.</p>
                </div>
                <div class="bg-ps2card p-4">
                    <h3 class="mb-1"><i class="fa-brands fa-reddit-alien"></i> Subreddit</h3>
                    <p>Type its name (<span class="font-mono-custom text-cyan-300">ps2</span>, <span class="font-mono-custom text-cyan-300">r/ps2</span>) or paste its link. Keep the suggested group: subreddits in one group are read together, because Reddit only allows about one request a minute.</p>
                </div>
            </div>
            <p>Made a typo? A source you just added has a <i class="fa-solid fa-trash-can"></i> button until you save. Sources that are already saved can only be switched off, so nothing gets lost by accident.</p>
        </section>

        <section id="weights" class="space-y-3">
            <h2>6. Weights</h2>
            <p>A weight says how much a source's items count towards the <b class="text-white">overall mood</b> figure. It doesn't change a single headline's own score, and it doesn't affect which games are recognised.</p>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-xs">
                    <thead><tr class="border-b border-slate-800"><th class="py-2 pr-3">WEIGHT</th><th class="py-2">MEANING</th></tr></thead>
                    <tbody>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 font-mono-custom text-white">1.5</td><td class="py-2">counts one and a half times: PS2-only sources such as r/ps2 and PS2 channels</td></tr>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 font-mono-custom text-white">1</td><td class="py-2">normal: news, official channels, Reddit, retro channels</td></tr>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 font-mono-custom text-white">0.5</td><td class="py-2">counts half: collectors and resellers ("INSANE PS2 HAUL!!") and big entertainment channels</td></tr>
                        <tr><td class="py-2 pr-3 font-mono-custom text-white">0</td><td class="py-2">still shown in the table, but doesn't count at all</td></tr>
                    </tbody>
                </table>
            </div>
            <ul class="list-disc pl-5 space-y-1">
                <li><b class="text-white">Change a whole kind of source</b> in the <b class="text-white">Weights &amp; schedule</b> tab, e.g. set <i>Collectors &amp; resellers</i> to 0.2.</li>
                <li><b class="text-white">Change a single source</b> by typing a number in its <b class="text-white">Weight</b> box. Leave it empty to use its role's weight.</li>
                <li>The dashboard updates immediately. Save to keep it.</li>
            </ul>
            <p>A PS2-only source does one other thing: the robot treats anything it publishes as being about the PS2, which helps it recognise games with short or ordinary names like <i>Ico</i> or <i>Black</i> that it would otherwise ignore.</p>
            <p>The same tab has the <b class="text-white">fetch schedule</b>: how often each kind of source is read. Podcasts are read about every 6 hours because their feeds are large; everything else about every hour (GitHub sometimes runs the robot a little late).</p>
        </section>

        <section id="save" class="space-y-3">
            <h2>7. Save your changes</h2>
            <p>The list of sources is a file called <span class="font-mono-custom text-cyan-300">feeds.json</span> on GitHub. Saving means putting the new version there, which needs a GitHub account that can edit the repository.</p>
            <ol class="steps list-decimal pl-5 space-y-2">
                <li>Press <b class="text-white"><i class="fa-solid fa-floppy-disk"></i> Save changes</b>. Your changes are copied and a box with the next steps appears.</li>
                <li>Click <b class="text-white">Open feeds.json on GitHub</b> (sign in if GitHub asks).</li>
                <li>Click inside the file, press <kbd>Ctrl</kbd>+<kbd>A</kbd> to select everything, then <kbd>Ctrl</kbd>+<kbd>V</kbd> to paste. On a Mac: <kbd>⌘</kbd>+<kbd>A</kbd>, <kbd>⌘</kbd>+<kbd>V</kbd>.</li>
                <li>Click the green <b class="text-white">Commit changes...</b> button, then <b class="text-white">Commit changes</b> again.</li>
                <li>Back on the dashboard, click <b class="text-white">I've saved it</b> to clear the badge.</li>
            </ol>
            <p>The robot starts by itself and new results appear within a few minutes.</p>
            <p>Select <i>everything</i> before pasting. Pasting into the middle of the file leaves a mixture of the old and new lists, which the robot refuses to read — it keeps the previous data until the file is valid again.</p>
            <p>If GitHub first asks you to <b class="text-white">Fork this repository</b>, your account can't edit it directly. That still works: click <b class="text-white">Fork this repository</b>, paste as above, click <b class="text-white">Propose changes</b>, then <b class="text-white">Create pull request</b>. The owner gets a request, and your change applies once they accept it. You can also press <b class="text-white">Download</b> on the dashboard and send the file to the owner.</p>
            <p class="text-slate-400"><i class="fa-solid fa-user-shield"></i> Commits made on github.com use your account's email settings. To keep your email private, turn on <b>Keep my email addresses private</b> in <a class="text-cyan-400 hover:underline" href="https://github.com/settings/emails" target="_blank" rel="noopener noreferrer">GitHub email settings</a>.</p>
        </section>

        <section id="token" class="space-y-3">
            <h2>8. One-click saving with a token (optional)</h2>
            <p>A token is a password that lets this page save for you. With one, <b class="text-white">Save changes</b> saves in one click and <b class="text-white">Run scraper now</b> works. Which kind you need depends on who owns the repository:</p>
            <div class="grid gap-4 sm:grid-cols-2">
                <div class="bg-ps2card p-4">
                    <h3 class="mb-2">The repository is yours</h3>
                    <ol class="steps list-decimal pl-5 space-y-1">
                        <li>Open <a class="text-cyan-400 hover:underline" href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener noreferrer">new fine-grained token</a>.</li>
                        <li>Name it "PS2 dashboard" and pick an expiry (e.g. 90 days).</li>
                        <li>Under <b class="text-white">Repository access</b> choose <b class="text-white">Only select repositories</b> and pick this repository.</li>
                        <li>Under <b class="text-white">Permissions</b> set <b class="text-white">Contents</b> to <b class="text-white">Read and write</b> (and <b class="text-white">Actions</b> too, for Run scraper now).</li>
                        <li>Press <b class="text-white">Generate token</b> and copy it (it starts with <span class="font-mono-custom">github_pat_</span>).</li>
                    </ol>
                </div>
                <div class="bg-ps2card p-4">
                    <h3 class="mb-2">You're a collaborator on someone else's repository</h3>
                    <ol class="steps list-decimal pl-5 space-y-1">
                        <li>GitHub doesn't allow fine-grained tokens here, so open <a class="text-cyan-400 hover:underline" href="https://github.com/settings/tokens/new" target="_blank" rel="noopener noreferrer">new classic token</a>.</li>
                        <li>Name it "PS2 dashboard" and pick an expiry (e.g. 90 days).</li>
                        <li>Tick only <b class="text-white">public_repo</b>. That is enough to save, but it covers all your public repositories, so keep the expiry short. Run scraper now would need the much broader <b class="text-white">repo</b> box; you don't need it because saving starts the scraper anyway.</li>
                        <li>Press <b class="text-white">Generate token</b> and copy it (it starts with <span class="font-mono-custom">ghp_</span>).</li>
                    </ol>
                </div>
            </div>
            <p>Then, on the dashboard: <b class="text-white">Sources &amp; Weights → GitHub settings</b>, paste the token, check that the repository is filled in (it is on the website) and press <b class="text-white">Save settings</b>. Tick <b class="text-white">Remember on this device</b> only on your own computer: it keeps the token in this browser for the whole github.io site.</p>
            <p class="text-slate-400"><i class="fa-solid fa-lock"></i> The token works like a password: don't share it. This page keeps it in your browser and only sends it to GitHub. <b>Forget token</b> removes it from the browser. You can cancel a token at any time in GitHub's settings: <a class="text-cyan-400 hover:underline" href="https://github.com/settings/personal-access-tokens" target="_blank" rel="noopener noreferrer">fine-grained tokens</a> or <a class="text-cyan-400 hover:underline" href="https://github.com/settings/tokens" target="_blank" rel="noopener noreferrer">classic tokens</a>. Saves made with a token use your GitHub no-reply email.</p>
        </section>

        <section id="status" class="space-y-3">
            <h2>9. What the status badges mean</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-xs">
                    <tbody>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 whitespace-nowrap"><span class="px-2 py-0.5 border text-emerald-400 border-emerald-900">Active</span></td><td class="py-2">published something in the last 2 weeks</td></tr>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 whitespace-nowrap"><span class="px-2 py-0.5 border text-slate-300 border-slate-700">Quiet</span></td><td class="py-2">nothing new for 2 weeks to 4 months</td></tr>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 whitespace-nowrap"><span class="px-2 py-0.5 border text-red-400 border-red-900">Stale</span></td><td class="py-2">nothing new for over 4 months; you may want to switch it off</td></tr>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 whitespace-nowrap"><span class="px-2 py-0.5 border text-red-400 border-red-900">Failing</span></td><td class="py-2">the last attempt to read it failed; hover the badge for details</td></tr>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 whitespace-nowrap"><span class="px-2 py-0.5 border text-slate-500 border-slate-700">Not checked yet</span></td><td class="py-2">the robot hasn't read it yet since it was added (a source you switch back on shows its last known status until the next run)</td></tr>
                        <tr class="border-b border-slate-800/60"><td class="py-2 pr-3 whitespace-nowrap"><span class="px-2 py-0.5 border text-slate-500 border-slate-700">OK · no dated items</span></td><td class="py-2">it can be read, but its items carry no dates, so its activity can't be judged</td></tr>
                        <tr><td class="py-2 pr-3 whitespace-nowrap"><span class="px-2 py-0.5 border text-slate-500 border-slate-700">Off</span></td><td class="py-2">switched off</td></tr>
                    </tbody>
                </table>
            </div>
        </section>

        <section id="problems" class="space-y-3">
            <h2>10. If something looks wrong</h2>
            <dl class="space-y-3">
                <div><dt class="text-white font-semibold">A new source still says "Not checked yet"</dt>
                    <dd>The robot runs every hour and right after a save. Wait a few minutes and press <b class="text-white">Refresh Feed</b>. The website itself can take a few minutes to show a new save.</dd></div>
                <div><dt class="text-white font-semibold">A headline is matched to the wrong game</dt>
                    <dd>It happens: the robot matches words, so a headline about a different game with a similar name can slip through. Wrong matches drop out by themselves within two weeks as old items age out of the feed. If you see the same wrong match again and again, it's worth reporting.</dd></div>
                <div><dt class="text-white font-semibold">A YouTube channel says "Failing: channel link..."</dt>
                    <dd>The link didn't lead to a channel. Open it to check. You can also add the channel by its ID: on the channel page open <b>more about this channel → Share channel → Copy channel ID</b> and paste that (it starts with UC).</dd></div>
                <div><dt class="text-white font-semibold">"Failing: already listed as ..."</dt>
                    <dd>That channel is already in the list under another name. Switch the new one off.</dd></div>
                <div><dt class="text-white font-semibold">A site or podcast says "Failing: HTTP 403" or "HTTP 404"</dt>
                    <dd>The site blocks the robot or moved its feed. Switch it off, or add its new feed link.</dd></div>
                <div><dt class="text-white font-semibold">"feeds.json was changed on GitHub after this page loaded"</dt>
                    <dd>Someone else saved in the meantime. Reload the page and make your change again, so theirs isn't lost.</dd></div>
                <div><dt class="text-white font-semibold">"Unsaved changes" doesn't go away</dt>
                    <dd>Finish the save steps and click <b class="text-white">I've saved it</b>, or press <b class="text-white">Discard</b> to go back to the saved list.</dd></div>
            </dl>
        </section>

        <section id="faq" class="space-y-3">
            <h2>11. Questions</h2>
            <dl class="space-y-3">
                <div><dt class="text-white font-semibold">Why are some of the biggest YouTube channels switched off?</dt>
                    <dd>Most are in other languages (the mood score only understands English) or mostly play Minecraft, Roblox or Fortnite, which says little about PS2 games. They are all in the list, so switch any of them on if you want.</dd></div>
                <div><dt class="text-white font-semibold">Does this page know any prices?</dt>
                    <dd>No. The amber buttons are searches that open a shop or price guide with the game already looked up. Nothing is stored here, so no price on this page can be out of date — but equally, you have to click through to see one.</dd></div>
                <div><dt class="text-white font-semibold">Why is a game high in Most Mentioned but missing from the Demand Index?</dt>
                    <dd>They measure different things. Most Mentioned counts what the sources here are talking about; the Demand Index counts what people are reading about on Wikipedia. A game can be all over the news without anyone looking it up, and the other way round.</dd></div>
                <div><dt class="text-white font-semibold">Where do the subscriber and rating numbers come from?</dt>
                    <dd>They were measured from YouTube and Apple Podcasts when the lists were made. See the ranked lists in <a class="text-cyan-400 hover:underline" data-repo-file="SOURCES.md" href="SOURCES.md">SOURCES.md</a>.</dd></div>
                <div><dt class="text-white font-semibold">Can I break something?</dt>
                    <dd>Hardly. The page checks the list before saving, the robot refuses a broken list and keeps the old data, and GitHub keeps every earlier version of the file.</dd></div>
                <div><dt class="text-white font-semibold">How does it work under the hood?</dt>
                    <dd>See <a class="text-cyan-400 hover:underline" data-repo-file="docs/ARCHITECTURE.md" href="docs/ARCHITECTURE.md">How it works</a>.</dd></div>
            </dl>
        </section>

        <p class="text-center pt-4">
            <a href="index.html#sourcesSection" class="inline-flex items-center gap-2 from-blue-600 text-xs px-4 py-2">
                <i class="fa-solid fa-arrow-left"></i> Back to the dashboard
            </a>
        </p>
    </main>

    <footer class="border-t border-ps2border py-6 mt-12 text-center text-xs text-slate-500">
        <p>PS2 Global Sentiment &amp; Remaster Tracker &bull; How to use</p>
    </footer>

    <script>
        // On GitHub Pages, point the docs links at GitHub, where Markdown is rendered.
        (function () {
            const owner = location.hostname.match(/^([a-z0-9-]+)\.github\.io$/i)?.[1];
            if (!owner) return;
            const first = location.pathname.split('/').filter(Boolean)[0];
            const repo = `${owner}/${first && !/\.html?$/i.test(first) ? first : `${owner}.github.io`}`;
            document.querySelectorAll('[data-repo-file]').forEach(link => {
                link.href = `https://github.com/${repo}/blob/main/${link.dataset.repoFile}`;
            });
        })();
    </script>
</body>
</html>
