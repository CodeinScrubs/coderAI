import pytest
from skills_manager import SkillsManager, get_skills_manager
import web_app


def test_detect_skill_commands_start_and_inline():
    sm = get_skills_manager()
    all_skills = sm.all()
    assert len(all_skills) > 0

    first_skill = all_skills[0]
    second_skill = all_skills[1] if len(all_skills) > 1 else all_skills[0]

    # Test at start
    detected = sm.detect_skill_commands(f'/{first_skill.name} please do this task')
    assert len(detected) >= 1
    assert detected[0].name == first_skill.name

    # Test inline
    detected_inline = sm.detect_skill_commands(f'Please use /{first_skill.name} to complete the refactor')
    assert len(detected_inline) >= 1
    assert detected_inline[0].name == first_skill.name

    # Test multiple
    detected_multi = sm.detect_skill_commands(f'/{first_skill.name} and then /{second_skill.name} check code')
    names = [s.name for s in detected_multi]
    assert first_skill.name in names
    if len(all_skills) > 1:
        assert second_skill.name in names


def test_strip_commands():
    sm = get_skills_manager()
    all_skills = sm.all()
    first_skill = all_skills[0]

    cleaned = sm.strip_commands(f'/{first_skill.name} please do this task')
    assert f'/{first_skill.name}' not in cleaned
    assert 'please do this task' in cleaned

    cleaned_inline = sm.strip_commands(f'Please use /{first_skill.name} to complete the refactor')
    assert f'/{first_skill.name}' not in cleaned_inline
    assert 'Please use' in cleaned_inline


def test_skills_payload_structure():
    payload = web_app._skills_payload()
    assert isinstance(payload, list)
    assert len(payload) > 0
    first = payload[0]
    assert 'name' in first
    assert 'slash_command' in first
    assert first['slash_command'].startswith('/')
    assert 'description' in first
    assert 'category' in first


def test_prepare_skill_turn_with_slash_command():
    sm = get_skills_manager()
    skill = sm.all()[0]
    clean_prompt, selections, auto_injection, turn_index = web_app._prepare_skill_turn(f'/{skill.name} build a feature')
    selected_names = [s.skill.name for s in selections]
    assert skill.name in selected_names
    assert auto_injection != ''
    assert skill.name in auto_injection
