import json

from backend.annotations.policy import DEFAULT_PATH, base_id, load_policy


def write(tmp_path, body):
    p = tmp_path / "policy.json"
    p.write_text(body if isinstance(body, str) else json.dumps(body))
    return p


def test_classification_uses_the_id_before_the_version_suffix(tmp_path):
    pol = load_policy(write(tmp_path, {"public": ["a1", "b2"], "heldout": ["b2"]}))
    assert pol.classify("a1-deadbeef") == "reference-only"
    assert pol.classify("b2-1234") == "heldout"
    assert pol.classify("b2") == "heldout"
    assert pol.classify("mycustom") == "train-ok"
    assert pol.classify("my-custom-env") == "train-ok"


def test_malformed_json_refuses_everything(tmp_path):
    pol = load_policy(write(tmp_path, "{not json"))
    assert pol.error and pol.classify("anything") == "heldout"
    assert "unusable" in pol.refusal("anything")


def test_missing_file_and_missing_keys_refuse_everything(tmp_path):
    assert load_policy(tmp_path / "nope.json").classify("x") == "heldout"
    assert load_policy(write(tmp_path, {"public": []})).classify("x") == "heldout"


def test_refusal_names_the_game_and_says_play_is_still_fine(tmp_path):
    pol = load_policy(write(tmp_path, {"public": ["g"], "heldout": ["g"]}))
    msg = pol.refusal("g-1")
    assert "g-1" in msg and "held-out" in msg and "without annotating" in msg


def test_base_id():
    assert base_id("r11l-495a7899") == "r11l" and base_id("tst1") == "tst1"


def test_shipped_policy_matches_adr_0009():
    pol = load_policy(DEFAULT_PATH)
    assert pol.error is None
    assert pol.heldout == {"ar25", "cn04", "g50t", "lp85", "r11l", "sb26", "sp80", "tr87", "wa30"}
    assert pol.heldout <= pol.public and len(pol.public) == 25
    assert pol.classify("ls20-abc") == "reference-only"
