from app.audit import _resource_type_and_id


def test_resource_type_and_id_extracts_resource_and_uuid():
    resource_type, resource_id = _resource_type_and_id("/api/v1/campaigns/11111111-1111-4111-8111-111111111111/launch")
    assert resource_type == "campaigns"
    assert resource_id == "11111111-1111-4111-8111-111111111111"


def test_resource_type_and_id_handles_no_id_in_path():
    resource_type, resource_id = _resource_type_and_id("/api/v1/contacts")
    assert resource_type == "contacts"
    assert resource_id is None


def test_resource_type_and_id_handles_short_path():
    resource_type, resource_id = _resource_type_and_id("/api/v1")
    assert resource_type == "unknown"


def test_resource_type_and_id_picks_first_uuid_segment():
    resource_type, resource_id = _resource_type_and_id(
        "/api/v1/campaigns/11111111-1111-4111-8111-111111111111/contacts/22222222-2222-4222-8222-222222222222"
    )
    assert resource_type == "campaigns"
    assert resource_id == "11111111-1111-4111-8111-111111111111"
