"""The pages load a built stylesheet (tailwind.css, tailwind-guide.css) instead of Tailwind's Play CDN script.

The build needs a browser (tools/build_tailwind.mjs), so these tests only check what can go wrong
without one: a page that still loads the CDN, a built file that is missing, and a Tailwind class that
was added to a page but not built (the page would show it unstyled).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = {"index.html": "tailwind.css", "guide.html": "tailwind-guide.css"}
# Utility classes whose names a built file must hold. A class with a prefix such as md: or hover: is
# looked up whole. Anything retro.css styles itself is not Tailwind's.
UTILITY = re.compile(
    r"^(?:[a-z-]+:)*-?(?:bg|text|border|p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|gap|gap-x|gap-y|space-x|space-y|w|h|min-w|min-h|"
    r"max-w|max-h|rounded|opacity|z|top|left|right|bottom|inset|grid-cols|col-span|row-span|tracking|leading|"
    r"shadow|ring|divide|order|basis|flex|grow|shrink|line-clamp|decoration|underline-offset|selection)-[\w\[\]./#%:,()-]+$")


def escaped(token):
    """The token as a Tailwind selector writes it (.md\\:flex, .w-1\\/2)."""
    return "." + re.sub(r"([^\w-])", r"\\\1", token)


def class_tokens(html):
    out = set()
    for value in re.findall(r'\bclass="([^"$`{}]*)"', html):
        out.update(value.split())
    return out


class TailwindBuildTests(unittest.TestCase):
    def test_pages_load_the_built_file_not_the_cdn(self):
        for page, css in PAGES.items():
            html = (ROOT / page).read_text(encoding="utf-8")
            self.assertNotIn("cdn.tailwindcss.com", html, f"{page} still loads the Play CDN")
            self.assertNotIn("tailwind.config", html, f"{page} still configures the Play CDN")
            self.assertRegex(html, rf'<link rel="stylesheet" href="{re.escape(css)}\?v=\w+">', f"{page} does not link {css}")
            self.assertTrue((ROOT / css).is_file(), f"{css} is missing")

    def test_built_files_are_real_and_hold_the_page_colours(self):
        index = (ROOT / "tailwind.css").read_text(encoding="utf-8")
        guide = (ROOT / "tailwind-guide.css").read_text(encoding="utf-8")
        self.assertIn("tools/build_tailwind.mjs", index.splitlines()[0])
        for css in (index, guide):
            self.assertIn("box-sizing", css, "the base reset is missing")
            self.assertIn(".bg-ps2dark", css)
        self.assertIn(".bg-spindle-red", index + (ROOT / "retro.css").read_text(encoding="utf-8")) if ".bg-spindle-red" in (ROOT / "index.html").read_text(encoding="utf-8") else None
        self.assertIn("JetBrains Mono", index, "index.html's font-mono is the site's mono face")

    def test_every_tailwind_class_in_the_markup_is_built(self):
        retro = (ROOT / "retro.css").read_text(encoding="utf-8")
        for page, css in PAGES.items():
            built = (ROOT / css).read_text(encoding="utf-8")
            html = (ROOT / page).read_text(encoding="utf-8")
            missing = sorted(t for t in class_tokens(html)
                             if UTILITY.match(t) and escaped(t) not in built and f".{t}" not in retro)
            self.assertEqual(missing, [], f"{page} uses classes {css} lacks: run tools/build_tailwind.mjs")


if __name__ == "__main__":
    unittest.main()
