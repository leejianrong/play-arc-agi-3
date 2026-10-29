from backend.custom_games import sync_custom_games


def make_game(root, name, body="class X: pass\n", meta='{"game_id": "x"}'):
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.py").write_text(body)
    (d / "metadata.json").write_text(meta)
    return d


def test_copies_games_with_metadata_and_reports_them(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    make_game(src, "alpha")
    make_game(src, "beta")
    assert sync_custom_games(src, dest) == ["alpha", "beta"]
    assert (dest / "alpha" / "alpha.py").read_text() == "class X: pass\n"
    assert (dest / "beta" / "metadata.json").exists()


def test_is_idempotent_and_updates_only_what_changed(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    make_game(src, "alpha")
    make_game(src, "beta")
    sync_custom_games(src, dest)
    assert sync_custom_games(src, dest) == []
    (src / "beta" / "beta.py").write_text("class Y: pass\n")
    assert sync_custom_games(src, dest) == ["beta"]
    assert (dest / "beta" / "beta.py").read_text() == "class Y: pass\n"


def test_skips_folders_without_metadata_and_never_deletes_other_games(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    (src / "notagame").mkdir(parents=True)
    (src / "notagame" / "x.py").write_text("")
    (dest / "ls20" / "9607627b").mkdir(parents=True)  # a downloaded real game must be left alone
    (dest / "ls20" / "9607627b" / "ls20.py").write_text("real")
    assert sync_custom_games(src, dest) == []
    assert not (dest / "notagame").exists()
    assert (dest / "ls20" / "9607627b" / "ls20.py").read_text() == "real"


def test_missing_source_directory_is_not_an_error(tmp_path):
    assert sync_custom_games(tmp_path / "nope", tmp_path / "dest") == []
