"""Homepage questions: broad source bank and no-repeat randomized rotation."""
import ast
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_question_bank_covers_all_move_families_and_history():
    questions = [line.strip() for line in
                 (ROOT / "data/homepage_prompt_questions.txt").read_text().splitlines()
                 if line.strip()]
    assert len(questions) == 260
    assert len(questions) == len({q.casefold() for q in questions})
    for subject in (
        "chant", "combos", "Bad One",
        "Good One", "Jo Smooth Bad One", "hat tricks", "footwork",
        "ankle moves", "Baby O Step", "Spank moves", "Public Enemies",
        "songs", "producer", "battle", "event", "archive", "Lock In",
    ):
        assert any(subject.casefold() in q.casefold() for q in questions), subject
    assert not any("the Ledger" in q for q in questions)


def test_homepage_prompt_picker_rotates_all_active_before_repeating():
    # Extract the real standalone picker without importing the production app.
    source = (ROOT / "app.py").read_text()
    tree = ast.parse(source)
    picker = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "hp_pick_prompt")
    code = compile(ast.Module(body=[picker], type_ignores=[]), "<hp_picker>", "exec")
    session = {}
    prompts = [{"id": i, "question": f"Question {i}"} for i in range(1, 21)]
    env = {"hp_active_prompts": lambda: list(prompts),
           "session": session, "_hp_random": random}
    exec(code, env)
    got = [env["hp_pick_prompt"]()["id"] for _ in prompts]
    assert set(got) == {p["id"] for p in prompts}
    assert len(set(got)) == len(prompts)
    assert session["homepage_prompt_cycle_index"] == len(prompts)
    assert env["hp_pick_prompt"]()["id"] in set(got)
    prompts.append({"id": 21, "question": "A new chant"})
    got = [env["hp_pick_prompt"]()["id"] for _ in prompts]
    assert set(got) == {p["id"] for p in prompts}


def test_homepage_prompt_keeps_question_active_after_submission():
    source = (ROOT / "app.py").read_text()
    part = source[source.index("def hp_home_widget():"):
                  source.index("def hp_widget_css():")]
    assert 'session.pop("homepage_prompt_answered_once", False)' in part
    assert "Another question" in part
    assert "LiteFeet Vault / Community Question" in part
    assert "return \"\"\"\n            <section class=\"homepage-prompt-widget homepage-prompt-thanks\"" not in part
    assert "Your answer was saved" in part


def test_homepage_question_curation_deactivates_only_retired_questions():
    questions = [line.strip() for line in
                 (ROOT / "data/homepage_prompt_questions.txt").read_text().splitlines()
                 if line.strip()]
    retired = [line.strip() for line in
               (ROOT / "data/homepage_prompt_retired_questions.txt").read_text().splitlines()
               if line.strip()]
    chants = [line for line in questions if "chant" in line.lower()]
    assert chants == [
        "What's your favorite chant?",
        "What chant don't you hear anymore?",
        "Which team has the best chant, and what is it?",
    ]
    assert len(retired) == 83
    assert not set(questions).intersection(retired)
    assert "What combo did your team use?" in retired
    assert "Who hosted the battle?" in retired
    assert "Do you remember the date or year of a battle?" in retired
    assert "What LiteFeet chants do you know?" in retired
    import ast
    app_ast = ast.parse((ROOT / "app.py").read_text())
    seed = next(node for node in app_ast.body
                if isinstance(node, ast.FunctionDef) and
                node.name == "hp_seed_prompts_from_file")
    import inspect
    body = ast.get_source_segment((ROOT / "app.py").read_text(), seed)
    assert "UPDATE homepage_prompts" in body
    assert "SET is_active = 0" in body
    assert "homepage_prompt_answers" not in body
    assert "DELETE FROM" not in body
