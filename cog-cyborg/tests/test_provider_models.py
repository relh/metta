from __future__ import annotations

import json

from cog_cyborg.providers import CodeReviewResponse, coerce_code_review_response


def test_coerce_code_review_response_accepts_wrapped_json() -> None:
    response = coerce_code_review_response(
        "\n".join(
            [
                "Model output:",
                (
                    "{\"set_policy\":\"def step(sdk):\\\\n    return {'role': 'miner'}\","
                    '"replace_scratchpad":"Cover east lane."}'
                ),
            ]
        )
    )

    assert response.action == "memory_and_policy"
    assert response.set_policy is not None
    assert response.replace_scratchpad == "Cover east lane."


def test_coerce_code_review_response_accepts_model_instance() -> None:
    response = coerce_code_review_response(CodeReviewResponse(action="memory", replace_scratchpad="Retreat to hub."))

    assert response.action == "memory"
    assert response.replace_scratchpad == "Retreat to hub."


def test_coerce_code_review_response_infers_action_without_explicit_action_field() -> None:
    response = coerce_code_review_response(
        {
            "set_policy": 'def step(sdk):\n    return {"role": "miner"}',
            "replace_plan": "# Plan\n- Open coverage",
        }
    )

    assert response.action == "memory_and_policy"
    assert response.set_policy == 'def step(sdk):\n    return {"role": "miner"}'
    assert response.replace_plan == "# Plan\n- Open coverage"


def test_coerce_code_review_response_promotes_none_action_when_canonical_fields_update_files() -> None:
    response = coerce_code_review_response(
        {
            "action": "none",
            "set_policy": 'def step(sdk):\n    return {"role": "miner"}',
            "replace_scratchpad": "phase: resource_coverage",
            "replace_plan": "# Plan\n- Open coverage\n- Replan on contact",
            "review_summary": "Model wants to rotate east lane coverage.",
        }
    )

    assert response.action == "memory_and_policy"
    assert response.set_policy == 'def step(sdk):\n    return {"role": "miner"}'
    assert response.replace_scratchpad == "phase: resource_coverage"
    assert response.replace_plan == "# Plan\n- Open coverage\n- Replan on contact"
    assert response.review_summary == "Model wants to rotate east lane coverage."


def test_coerce_code_review_response_rejects_legacy_nested_payloads() -> None:
    response = coerce_code_review_response(
        "\n".join(
            [
                "```json",
                json.dumps(
                    {
                        "action": "memory_and_policy",
                        "set_policy": {"main.py": 'def step(sdk):\n    return {"objective": "aligner_pressure"}'},
                        "replace_plan": {"plan.md": "# Plan\n- Save hearts\n- Rotate to pressure"},
                        "triggers": [{"name": "enemy_seen", "target": "policy"}],
                    }
                ),
                "```",
            ]
        )
    )

    assert response.action == "none"
    assert response.set_policy is None
    assert response.replace_plan is None
    assert response.triggers[0].name == "enemy_seen"


def test_coerce_code_review_response_promotes_none_action_when_payload_updates_files() -> None:
    response = coerce_code_review_response(
        {
            "action": "none",
            "set_policy": 'def step(sdk):\n    return {"role": "miner"}',
            "replace_scratchpad": "phase: resource_coverage",
        }
    )

    assert response.action == "memory_and_policy"
    assert response.set_policy == 'def step(sdk):\n    return {"role": "miner"}'
    assert response.replace_scratchpad == "phase: resource_coverage"


def test_coerce_code_review_response_promotes_partial_action_when_payload_adds_second_update() -> None:
    response = coerce_code_review_response(
        {
            "action": "memory",
            "set_policy": 'def step(sdk):\n    return {"objective": "aligner_pressure"}',
        }
    )

    assert response.action == "policy"
    assert response.set_policy == 'def step(sdk):\n    return {"objective": "aligner_pressure"}'


def test_coerce_code_review_response_accepts_canonical_plan_field() -> None:
    response = coerce_code_review_response(
        {
            "action": "memory",
            "replace_plan": "phase: economy_bootstrap\nnext: rebuild hearts",
        }
    )

    assert response.action == "memory"
    assert response.replace_plan == "phase: economy_bootstrap\nnext: rebuild hearts"
