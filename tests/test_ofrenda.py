"""Phase 2: deterministic notes, unique page names, escaping, links, repeatable builds."""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lastwords.cli import main
from lastwords.history import Author, CommitRecord
from lastwords.ofrenda import GENERATOR_MARK, build_site, line_facts, note, page_names, slugify


def ghost(name, *subjects, source=0, resource=0, email=None, seed=None):
    commits = [
        CommitRecord(
            sha=hashlib.sha1(f"{seed or name}{i}".encode()).hexdigest(),
            message=s,
            when=datetime(2015, 1, i + 1, tzinfo=timezone.utc),
            files=["app.py"],
        )
        for i, s in enumerate(subjects or ["Add a feature to the app"])
    ]
    return Author(name, email or f"{seed or name}@example.com", commits, source, resource)


def links(index_html: str) -> list[str]:
    return re.findall(r'<a class="card" href="([^"]+)"', index_html)


# --- notes -------------------------------------------------------------------

def test_note_is_exact_and_needs_no_model(fake_ollama):
    g = ghost("Eric Wieser", "Prevent syntax errors when line-wrapping comprehensions", source=74)
    assert note(g, "bottle") == (
        "Thank you, Eric Wieser, for “Prevent syntax errors when line-wrapping "
        "comprehensions”. 74 lines of their source code still run in bottle today."
    )
    assert fake_ollama.calls == []


def test_note_keeps_commit_message_exactly(fake_ollama):
    subject = 'Issue #727 demonstrate "oo" routing & <test> to break wsgi.input'
    assert f"“{subject}”" in note(ghost("Alex Collins", subject, source=39), "bottle")


def test_note_does_not_double_terminal_punctuation():
    g = ghost("Iuri de Silvio", "Stressing encoding definition. I swear I found these bugs by accident.", source=44)
    assert "by accident.” 44 lines" in note(g, "bottle")


@pytest.mark.parametrize("source, resource, expected", [
    (91, 9, "91 lines of their source code still run in bottle today, along with 9 lines in translation and generated files."),
    (20, 28921, "20 lines of their source code still run in bottle today, along with 28,921 lines in translation and generated files."),
    (0, 2114, "2,114 lines of their work in translation and generated files still ship with bottle today."),
    (1, 0, "1 line of their source code still runs in bottle today."),
    (0, 1, "1 line of their work in translation and generated files still ships with bottle today."),
    (0, 0, "Their commits remain part of bottle's history."),
])
def test_line_facts_counts_and_grammar(source, resource, expected):
    assert line_facts(ghost("X Y", source=source, resource=resource), "bottle") == expected


def test_note_never_mentions_death():
    text = note(ghost("Sam", "Remove the old parser", source=3), "proj").lower()
    for word in ("died", "passed away", "gone", "late ", "rest in", "memory of"):
        assert word not in text


# --- page names ----------------------------------------------------------------

def test_unicode_names_get_distinct_safe_names():
    ghosts = [ghost("张酉夫"), ghost("Роман Донченко"), ghost("花浅葱"), ghost("Michael Käufl")]
    names = page_names(ghosts)
    assert len(set(names)) == 4
    assert names[3] == "michael-kaufl"
    for n in names[:3]:
        assert re.fullmatch(r"ghost-[0-9a-f]{8}", n)
    assert all(re.fullmatch(r"[a-z0-9-]+", n) for n in names)


def test_identical_display_names_are_told_apart():
    a = ghost("Eric L Frederich", seed="one")
    b = ghost("Eric L Frederich", seed="two")
    c = ghost("Eric L. Frederich", seed="three")  # same slug, different name
    names = page_names([a, b, c])
    assert len(set(names)) == 3
    assert all(n.startswith("eric-l-frederich-") for n in names)
    assert names == page_names([a, b, c])  # stable


def test_punctuation_traversal_and_reserved_names():
    ghosts = [
        ghost("../../etc/passwd"), ghost("O'Brien & Co. <b>"), ghost("CON"),
        ghost("index"), ghost("..\\..\\Windows"), ghost("🕯️👻"), ghost("a" * 200),
    ]
    names = page_names(ghosts)
    assert len(set(names)) == len(names)
    for n in names:
        assert re.fullmatch(r"[a-z0-9-]+", n) and len(n) <= 70
    assert names[0] == "etc-passwd"
    assert names[1] == "o-brien-co-b"
    assert names[2].startswith("con-") and names[3].startswith("index-")
    assert names[5].startswith("ghost-")


def test_email_never_appears_in_page_names():
    g = ghost("张酉夫", email="secret.person@example.com")
    assert "secret" not in page_names([g])[0]


def test_slugify_transliterates_accents():
    assert slugify("Çağatay Tengiz") == "cagatay-tengiz"
    assert slugify("Frédéric Junod") == "frederic-junod"
    assert slugify("张酉夫") == ""


# --- built site ----------------------------------------------------------------

@pytest.fixture
def site_ghosts():
    return [
        ghost("张酉夫", "translate the docs", source=12),
        ghost("Роман Донченко", "Привет мир", resource=5),
        ghost("Michael Käufl", "docs: link to the Jinja2 website", source=30),
        ghost("Eric L Frederich", "<script>alert('x')</script> & fix", source=2, seed="one"),
        ghost("Eric L Frederich", "Second person, same name", source=1, seed="two"),
    ]


def test_index_links_all_resolve_and_are_unique(tmp_path, site_ghosts):
    out = build_site(site_ghosts, "proj", str(tmp_path / "site"))
    hrefs = links((out / "index.html").read_text(encoding="utf-8"))
    assert len(hrefs) == len(site_ghosts) == len(set(hrefs))
    for href in hrefs:
        assert (out / href).is_file()
    assert sorted(p.name for p in out.iterdir()) == sorted(hrefs + ["index.html"])


def test_pages_are_utf8_and_escape_html(tmp_path, site_ghosts):
    out = build_site(site_ghosts, "proj", str(tmp_path / "site"))
    for page in out.glob("*.html"):
        page.read_bytes().decode("utf-8")  # strict
    html = "".join(p.read_text(encoding="utf-8") for p in out.glob("*.html"))
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt; &amp; fix" in html
    assert "张酉夫" in html and "Привет мир" in html and "Michael Käufl" in html


def test_counts_shown_on_pages(tmp_path, site_ghosts):
    out = build_site(site_ghosts, "proj", str(tmp_path / "site"))
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "12 source lines still alive" in index
    assert "+ 5 in translation and generated files" in index
    roman = next(p for p in out.glob("ghost-*.html") if "Роман" in p.read_text(encoding="utf-8"))
    assert "5 lines of their work in translation and generated files" in roman.read_text(encoding="utf-8")


def test_repeated_builds_are_byte_identical(tmp_path, site_ghosts):
    a = build_site(site_ghosts, "proj", str(tmp_path / "a"))
    b = build_site(site_ghosts, "proj", str(tmp_path / "b"))
    files_a = {p.name: p.read_bytes() for p in a.iterdir()}
    files_b = {p.name: p.read_bytes() for p in b.iterdir()}
    assert files_a == files_b
    build_site(site_ghosts, "proj", str(a))  # rebuild in place
    assert {p.name: p.read_bytes() for p in a.iterdir()} == files_a


def test_rebuild_removes_only_its_own_stale_pages(tmp_path, site_ghosts):
    out = tmp_path / "site"
    build_site(site_ghosts, "proj", str(out))
    (out / "mine.html").write_text("<p>hand-written, keep me</p>", encoding="utf-8")
    build_site(site_ghosts[:2], "proj", str(out))
    names = sorted(p.name for p in out.iterdir())
    assert "mine.html" in names
    assert "michael-kaufl.html" not in names  # was ours, no longer listed
    assert len([n for n in names if n != "mine.html"]) == 3


def test_build_leaves_backup_untouched(tmp_path, site_ghosts):
    out = tmp_path / "site"
    backup = tmp_path / "backups" / "site-old"
    backup.mkdir(parents=True)
    (backup / "index.html").write_text(GENERATOR_MARK + " old index", encoding="utf-8")
    (backup / "thiago-avelino.html").write_text(GENERATOR_MARK + " old page", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in backup.iterdir()}
    build_site(site_ghosts, "proj", str(out))
    build_site(site_ghosts[:1], "proj", str(out))
    assert {p.name: p.read_bytes() for p in backup.iterdir()} == before


def test_footer_says_how_notes_were_made(tmp_path, site_ghosts, fake_ollama):
    plain = build_site(site_ghosts[:1], "proj", str(tmp_path / "a"))
    assert "Every note quotes a real commit message" in (plain / "index.html").read_text(encoding="utf-8")
    assert "open-weight model" not in (plain / "index.html").read_text(encoding="utf-8")
    ai = build_site(site_ghosts[:1], "proj", str(tmp_path / "b"), "m", ai_notes=True)
    assert "written locally by an open-weight model" in (ai / "index.html").read_text(encoding="utf-8")
    assert len(fake_ollama.calls) == 1


def test_cli_ofrenda_is_deterministic_by_default(make_repo, fake_ollama, tmp_path, capsys):
    repo = make_repo()
    repo.commit({"app.py": "1\n2\n"}, "Add the first feature", author="张酉夫 <z@example.com>")
    repo.commit({"x.po": "a\n"}, "Translate strings", author="Ana Lima <a@example.com>")
    args = ["ofrenda", str(repo.path), "--inactive-days", "30", "--out"]
    assert main(args + [str(tmp_path / "one")]) == 0
    assert main(args + [str(tmp_path / "two")]) == 0
    assert fake_ollama.calls == []
    one = {p.name: p.read_bytes() for p in (tmp_path / "one").iterdir()}
    two = {p.name: p.read_bytes() for p in (tmp_path / "two").iterdir()}
    assert one == two and len(one) == 3
