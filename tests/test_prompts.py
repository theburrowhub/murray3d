import json
from pathlib import Path

import pytest

from murray3d.prompts import (
    PromptError,
    iter_jobs,
    load_prompt_doc,
    parse_prompt_doc,
    resolve_name,
    snake_case,
)

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "prompts-miniaturas.sample.json"


def test_snake_case_handles_accents_spaces_symbols():
    assert snake_case("Kamehameha Cargando") == "kamehameha_cargando"
    assert snake_case("Súper Saiyan!") == "super_saiyan"
    assert snake_case("  A/B  C ") == "a_b_c"
    assert snake_case("") == ""


def test_sample_file_parses_and_counts():
    doc = load_prompt_doc(SAMPLE)
    assert len(doc.figures) == 3
    jobs = iter_jobs(doc)
    assert len(jobs) == 6
    assert doc.automation_config.image_generation.recommended_model == "flux-dev"
    assert doc.automation_config.image_generation.aspect_ratio == "3:4"


def test_naming_convention_with_variant_padding():
    doc = load_prompt_doc(SAMPLE)
    jobs = iter_jobs(doc)
    names = [j.output_name for j in jobs]
    assert "dragon_ball_goku_01_kamehameha_cargando" in names
    assert "dragon_ball_goku_02_super_saiyan_pose" in names
    assert "star_wars_darth_vader_01_lightsaber_ignited" in names


def test_iter_jobs_inherits_model_and_aspect_and_overrides():
    doc = load_prompt_doc(SAMPLE)
    jobs = iter_jobs(doc)
    assert all(j.model == "flux-dev" for j in jobs)
    assert all(j.aspect_ratio == "3:4" for j in jobs)
    over = iter_jobs(doc, model="mystic", aspect_ratio="1:1")
    assert all(j.model == "mystic" and j.aspect_ratio == "1:1" for j in over)


def test_duplicate_names_are_disambiguated():
    data = {
        "figures": [
            {"group": "G", "character": "C", "prompts": [
                {"id": 1, "variant": 1, "title": "Same", "prompt": "p1"},
                {"id": 2, "variant": 1, "title": "Same", "prompt": "p2"},
            ]}
        ]
    }
    doc = parse_prompt_doc(data)
    names = [j.output_name for j in iter_jobs(doc)]
    assert names[0] != names[1]
    assert names[1].endswith("_2")


def test_resolve_name_falls_back_on_bad_pattern():
    from murray3d.prompts import Figure, PromptSpec
    fig = Figure(group="G", character="C")
    spec = PromptSpec(id=7, variant=3, title="X Y", prompt="p")
    # patrón con token inexistente -> cae al patrón por defecto
    name = resolve_name("{no_such_token}", fig, spec)
    assert name == "g_c_03_x_y"


def test_missing_required_prompt_field_raises():
    with pytest.raises(PromptError):
        parse_prompt_doc({"figures": [{"prompts": [{"id": 1}]}]})  # falta 'prompt'


def test_load_invalid_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(PromptError):
        load_prompt_doc(bad)
