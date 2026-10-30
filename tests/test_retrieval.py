"""Fix 1: the blamed commit is always remembered, once, and citations are checked."""
from lastwords.channel import ask_ghost, build_prompt, check_citations, retrieve
from lastwords.cli import main
from lastwords.history import load_authors

QUESTION = "why does the router cache compiled routes?"


def ghost_repo(make_repo):
    repo = make_repo()
    shas = {}
    shas["blamed"] = repo.commit({"app.py": "x = 1\n"}, "Initial skeleton")
    # many keyword-rich commits that would outrank the blamed one
    for i in range(10):
        shas[f"noise{i}"] = repo.commit(
            {f"router{i}.py": f"y = {i}\n"},
            f"Router cache for compiled routes, part {i}",
            date=f"2015-04-{i + 1:02d}T12:00:00+00:00",
        )
    return repo, shas


def test_blamed_commit_included_even_without_keyword_overlap(make_repo):
    repo, shas = ghost_repo(make_repo)
    ghost = load_authors(str(repo.path))["ada ghost"]

    # keyword ranking alone pushes it out: this was the audit's 6/45 bug
    without = retrieve(ghost, QUESTION, "app.py")
    assert shas["blamed"] not in [m.sha for m in without]

    memories = retrieve(ghost, QUESTION, "app.py", blamed_sha=shas["blamed"])

    assert memories[0].sha == shas["blamed"]
    assert len(memories) == 6  # limit still respected
    assert all(m.sha.startswith(tuple(shas.values())) for m in memories)


def test_blamed_commit_alone_when_nothing_else_matches(make_repo):
    repo, shas = ghost_repo(make_repo)
    ghost = load_authors(str(repo.path))["ada ghost"]
    memories = retrieve(ghost, "zzz qqq", "nowhere.py", blamed_sha=shas["blamed"])
    assert [m.sha for m in memories] == [shas["blamed"]]


def test_no_duplicate_when_blamed_commit_also_ranks_high(make_repo):
    repo, shas = ghost_repo(make_repo)
    ghost = load_authors(str(repo.path))["ada ghost"]
    top = shas["noise9"]  # also the best keyword match
    memories = retrieve(ghost, QUESTION, "router9.py", blamed_sha=top)
    ids = [m.sha for m in memories]
    assert ids[0] == top
    assert len(ids) == len(set(ids))


def test_whole_word_matching_ignores_substrings(make_repo):
    repo = make_repo()
    repo.commit({"a.py": "a\n"}, "Improve __repr__ of Route")
    ghost = load_authors(str(repo.path))["ada ghost"]
    assert retrieve(ghost, "out", None) == []  # "out" is inside "Route", not a word


def test_prompt_is_chronological_and_marks_blamed_commit(make_repo):
    repo, shas = ghost_repo(make_repo)
    ghost = load_authors(str(repo.path))["ada ghost"]
    memories = retrieve(ghost, QUESTION, "app.py", blamed_sha=shas["blamed"])
    prompt = build_prompt(ghost, QUESTION, memories, shas["blamed"])
    lines = [l for l in prompt.splitlines() if l.startswith("- [")]
    dates = [l.split("] ")[1][:10] for l in lines]
    assert dates == sorted(dates)
    assert "wrote the line" in next(l for l in lines if shas["blamed"][:7] in l)


def test_check_citations_keeps_real_and_removes_invented(make_repo):
    repo, shas = ghost_repo(make_repo)
    ghost = load_authors(str(repo.path))["ada ghost"]
    memories = retrieve(ghost, QUESTION, "app.py", blamed_sha=shas["blamed"])
    real = shas["blamed"][:7]
    text, removed = check_citations(
        f"I wrote it in [{real}], then again in [deadbe7] and 0badc0ffee.", memories
    )
    assert f"[{real}]" in text
    assert "deadbe7" not in text and "0badc0ffee" not in text
    assert removed == ["deadbe7", "0badc0ffee"]


def test_check_citations_leaves_words_and_numbers_alone():
    text, removed = check_citations("They defaced 1234567 records in 2016.", [])
    assert text == "They defaced 1234567 records in 2016."
    assert removed == []


def test_ask_ghost_strips_invented_citation(make_repo, fake_ollama):
    repo, shas = ghost_repo(make_repo)
    ghost = load_authors(str(repo.path))["ada ghost"]
    fake_ollama.state["reply"] = f"See [{shas['blamed'][:7]}] and [abcdef1]."
    answer, memories = ask_ghost(ghost, QUESTION, "m", "app.py", blamed_sha=shas["blamed"])
    assert "[abcdef1]" not in answer
    assert f"[{shas['blamed'][:7]}]" in answer
    assert "removed 1 citation" in answer
    cited = {m.sha[:7] for m in memories}
    assert shas["blamed"][:7] in cited


def test_cli_ask_sends_blamed_commit_to_model(make_repo, fake_ollama, capsys):
    repo, shas = ghost_repo(make_repo)
    code = main(["ask", str(repo.path), QUESTION, "--file", "app.py", "--line", "1", "--model", "m"])
    out = capsys.readouterr().out
    assert code == 0
    assert shas["blamed"][:7] in fake_ollama.calls[0]["prompt"]
    assert f"[{shas['blamed'][:7]}]" in out and "<- wrote this line" in out
