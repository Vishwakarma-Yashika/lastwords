"""Fix 4: expected failures give one line on stderr and a non-zero exit."""
import httpx
import ollama
import pytest

from lastwords import cli, history
from lastwords.cli import main


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def assert_clean_error(code, err, *needles):
    assert code == 1
    assert err.startswith("lastwords: error: ")
    assert "Traceback" not in err
    for needle in needles:
        assert needle in err


@pytest.fixture
def repo(make_repo):
    r = make_repo()
    r.commit({"app.py": "a\nb\nc\n", "pkg/mod.py": "m\n"}, "initial")
    return r


# --- repositories ---------------------------------------------------------

def test_missing_repository_folder(capsys, tmp_path):
    code, _, err = run(capsys, "summon", str(tmp_path / "nope"))
    assert_clean_error(code, err, "no such folder")


def test_folder_that_is_not_a_repository(capsys, tmp_path):
    code, _, err = run(capsys, "summon", str(tmp_path))
    assert_clean_error(code, err, "is not a git repository")


def test_repository_path_is_a_file(capsys, tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    code, _, err = run(capsys, "summon", str(f))
    assert_clean_error(code, err, "is a file")


def test_repository_without_commits(capsys, make_repo):
    empty = make_repo("empty")
    code, _, err = run(capsys, "summon", str(empty.path))
    assert_clean_error(code, err, "has no commits yet")


# --- files and lines ------------------------------------------------------

@pytest.mark.parametrize("file, line, needle", [
    ("missing.py", 1, "does not exist in the latest commit"),
    ("pkg", 1, "is a folder"),
    ("../outside.py", 1, "not a path inside the repository"),
    ("app.py", 0, "--line must be 1 or more"),
    ("app.py", -4, "--line must be 1 or more"),
    ("app.py", 4, "app.py has 3 lines; there is no line 4"),
])
def test_bad_file_or_line(capsys, repo, file, line, needle):
    code, _, err = run(capsys, "ask", str(repo.path), "q", "--file", file, "--line", str(line))
    assert_clean_error(code, err, needle)


def test_absolute_path_outside_repository(capsys, repo, tmp_path):
    outside = tmp_path / "elsewhere.py"
    outside.write_text("x")
    code, _, err = run(capsys, "ask", str(repo.path), "q", "--file", str(outside), "--line", "1")
    assert_clean_error(code, err, "is outside the repository")


def test_windows_style_and_absolute_paths_are_accepted(capsys, repo, fake_ollama):
    for file in ["pkg\\mod.py", str(repo.path / "pkg" / "mod.py")]:
        code, out, _ = run(capsys, "ask", str(repo.path), "q", "--file", file, "--line", "1")
        assert code == 0
        assert "Line 1 of pkg/mod.py" in out


def test_bad_line_is_reported_before_history_loads(capsys, repo, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("history was loaded before the line was checked")
    monkeypatch.setattr(cli, "load_authors", boom)
    monkeypatch.setattr(history, "load_authors", boom)
    code, _, err = run(capsys, "ask", str(repo.path), "q", "--file", "app.py", "--line", "99")
    assert_clean_error(code, err, "there is no line 99")


# --- Ollama ---------------------------------------------------------------

def ask(capsys, repo):
    return run(capsys, "ask", str(repo.path), "q", "--file", "app.py", "--line", "1", "--model", "gemma2:2b")


def test_ollama_not_running(capsys, repo, fake_ollama, monkeypatch):
    fake_ollama.state["reply"] = ConnectionError("Failed to connect to Ollama")
    monkeypatch.setattr("shutil.which", lambda name: "C:/Ollama/ollama.exe")
    code, _, err = ask(capsys, repo)
    assert_clean_error(code, err, "not answering", "ollama serve")


def test_ollama_not_installed(capsys, repo, fake_ollama, monkeypatch):
    fake_ollama.state["reply"] = ConnectionError("Failed to connect to Ollama")
    monkeypatch.setattr("shutil.which", lambda name: None)
    code, _, err = ask(capsys, repo)
    assert_clean_error(code, err, "Ollama is not installed", "ollama.com/download")


def test_ollama_timeout(capsys, repo, fake_ollama, monkeypatch):
    fake_ollama.state["reply"] = httpx.ReadTimeout("timed out")
    monkeypatch.setattr("shutil.which", lambda name: "ollama")
    code, _, err = ask(capsys, repo)
    assert_clean_error(code, err, "not answering")


def test_missing_model(capsys, repo, fake_ollama):
    fake_ollama.state["reply"] = ollama.ResponseError("model 'gemma2:2b' not found", 404)
    code, _, err = ask(capsys, repo)
    assert_clean_error(code, err, "not installed in Ollama", "ollama pull gemma2:2b")


def test_generation_error(capsys, repo, fake_ollama):
    fake_ollama.state["reply"] = ollama.ResponseError("out of memory", 500)
    code, _, err = ask(capsys, repo)
    assert_clean_error(code, err, "could not generate", "out of memory")


# --- output folder --------------------------------------------------------

def test_output_path_is_a_file(capsys, repo, tmp_path, monkeypatch):
    target = tmp_path / "taken"
    target.write_text("x")
    monkeypatch.setattr(cli, "load_authors", lambda *a: pytest.fail("loaded history first"))
    code, _, err = run(capsys, "ofrenda", str(repo.path), "--out", str(target))
    assert_clean_error(code, err, "is a file, not a folder")


def test_output_path_cannot_be_created(capsys, repo, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    code, _, err = run(capsys, "ofrenda", str(repo.path), "--out", str(blocker / "site"))
    assert_clean_error(code, err, "cannot write to --out")


# --- success paths are unchanged ------------------------------------------

def test_successful_commands_exit_zero(capsys, repo, fake_ollama, tmp_path):
    assert main(["summon", str(repo.path), "--inactive-days", "30"]) == 0
    assert "ghosts walk this repo" in capsys.readouterr().out
    out_dir = tmp_path / "site"
    assert main(["ofrenda", str(repo.path), "--out", str(out_dir), "--inactive-days", "30"]) == 0
    assert (out_dir / "index.html").exists() and (out_dir / "ada-ghost.html").exists()
