"""Fix 5: .mailmap identities, idempotent counts, source vs generated lines."""
from lastwords.history import count_surviving_lines, find_ghosts, is_generated, load_authors


def test_counts_are_the_same_when_computed_twice(make_repo):
    repo = make_repo()
    repo.commit({"a.py": "1\n2\n3\n"}, "three lines")
    authors = load_authors(str(repo.path))
    count_surviving_lines(str(repo.path), authors)
    first = {k: (a.surviving_lines, a.resource_lines) for k, a in authors.items()}
    count_surviving_lines(str(repo.path), authors)
    assert {k: (a.surviving_lines, a.resource_lines) for k, a in authors.items()} == first
    assert first == {"ada ghost": (3, 0)}


def test_mailmap_merges_identities_and_keeps_original_metadata(make_repo):
    repo = make_repo()
    repo.commit({"a.py": "a\n"}, "as old name", author="Old Handle <old@example.com>")
    repo.commit({"b.py": "b\nb\n"}, "as new name", author="Real Name <real@example.com>",
                date="2016-01-01T00:00:00+00:00")
    repo.commit({".mailmap": "Real Name <real@example.com> Old Handle <old@example.com>\n"},
                "add mailmap", author="Real Name <real@example.com>",
                date="2016-02-01T00:00:00+00:00")

    authors = load_authors(str(repo.path))
    assert set(authors) == {"real name"}
    person = authors["real name"]
    assert len(person.commits) == 3
    assert ("Old Handle", "old@example.com") in person.aliases
    oldest = person.first_commit
    assert (oldest.author_name, oldest.author_email) == ("Old Handle", "old@example.com")

    count_surviving_lines(str(repo.path), authors)
    assert person.surviving_lines == 3 + 1  # a.py, b.py, .mailmap


def test_without_mailmap_identities_stay_separate(make_repo):
    repo = make_repo()
    repo.commit({"a.py": "a\n"}, "one", author="Old Handle <old@example.com>")
    repo.commit({"b.py": "b\n"}, "two", author="Real Name <real@example.com>")
    assert set(load_authors(str(repo.path))) == {"old handle", "real name"}


def test_same_name_different_email_still_merges(make_repo):
    """Existing behaviour kept: the display name is the identity."""
    repo = make_repo()
    repo.commit({"a.py": "a\n"}, "work", author="Sam Lee <sam@work.example>")
    repo.commit({"b.py": "b\n"}, "home", author="Sam Lee <sam@home.example>")
    assert len(load_authors(str(repo.path))["sam lee"].commits) == 2


def test_generated_and_translation_lines_counted_separately(make_repo):
    repo = make_repo()
    repo.commit({
        "app.py": "1\n2\n3\n4\n",
        "locale/es/messages.po": "msgid \"a\"\nmsgstr \"b\"\n",
        "package-lock.json": "{}\n",
        "data/table.txt": "g1\ng2\ng3\n",
        ".gitattributes": "data/table.txt linguist-generated\n",
        "logo.png": b"\x89PNG\x00\x01\x02binary",
    }, "everything")
    authors = load_authors(str(repo.path))
    count_surviving_lines(str(repo.path), authors)
    ada = authors["ada ghost"]
    assert ada.surviving_lines == 4 + 1  # app.py + .gitattributes
    assert ada.resource_lines == 2 + 1 + 3  # .po + lock file + linguist-generated
    # nothing is silently dropped except binary files, which have no lines
    assert ada.surviving_lines + ada.resource_lines == 11


def test_is_generated_rules():
    assert is_generated("docs/_locale/zh_CN/LC_MESSAGES/api.po")
    assert is_generated("static/app.min.js")
    assert is_generated("Cargo.lock")
    assert not is_generated("bottle.py")
    assert is_generated("x.txt", {"x.txt": "set"})
    assert not is_generated("x.txt", {"x.txt": "unspecified"})


def test_ghosts_ranked_by_source_lines(make_repo):
    repo = make_repo()
    repo.commit({"t.po": "\n".join("x" * 50) + "\n"}, "translations", author="Tran Slator <t@example.com>")
    repo.commit({"a.py": "1\n2\n"}, "code", author="Code Writer <c@example.com>")
    authors = load_authors(str(repo.path))
    count_surviving_lines(str(repo.path), authors)
    order = [g.name for g in find_ghosts(authors, 30)]
    assert order == ["Code Writer", "Tran Slator"]
