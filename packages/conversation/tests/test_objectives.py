from jkr_conversation import objectives


def test_every_objective_matches_pre_refactor_field_keys():
    # Locks in the exact field keys that were hardcoded in
    # services/voice-worker/app/providers/mock.py's MOCK_SCRIPTS before this
    # refactor — a regression here would silently change what
    # AgentVersion.primary_objective values map onto.
    expected = {
        "qualify_and_route": ["topic", "preferred_callback_time"],
        "qualify_lead": ["interest_detail", "timeline"],
        "book_appointment": ["reason_for_visit", "preferred_date", "preferred_time"],
        "renewal_reminder": ["renewal_interest", "preferred_callback_time"],
        "collect_feedback": ["satisfaction", "improvement_area"],
    }
    for objective_id, field_keys in expected.items():
        assert objectives.all_field_keys(objective_id) == field_keys


def test_unknown_objective_falls_back_to_default():
    # Matches the old MOCK_SCRIPTS.get(objective, MOCK_SCRIPTS["qualify_and_route"]) fallback.
    assert objectives.get_objective("nonexistent_objective").id == objectives.DEFAULT_OBJECTIVE_ID


def test_book_appointment_is_tool_backed():
    assert objectives.get_objective("book_appointment").tool_on_completion == "book_appointment"


def test_other_objectives_are_not_tool_backed():
    for objective_id in ("qualify_and_route", "qualify_lead", "renewal_reminder", "collect_feedback"):
        assert objectives.get_objective(objective_id).tool_on_completion is None


def test_required_field_keys_excludes_optional_fields():
    # collect_feedback's improvement_area is deliberately optional.
    assert "improvement_area" not in objectives.required_field_keys("collect_feedback")
    assert "satisfaction" in objectives.required_field_keys("collect_feedback")


def test_every_field_has_all_three_languages():
    for objective in objectives.OBJECTIVES.values():
        for field in objective.fields:
            assert set(field.question.keys()) == {"te", "hi", "en"}
        assert set(objective.closing_text.keys()) == {"te", "hi", "en"}
