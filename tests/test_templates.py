from fastapi.testclient import TestClient

from app.main import create_app


REQUIRED_TEMPLATE_IDS = {
    "xianxia_rise",
    "apocalypse_base",
    "urban_ability",
    "infinity_trial",
    "detective_mystery",
}


def test_templates_returns_mvp_template_catalog() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/templates?locale=zh-Hans")

    assert response.status_code == 200
    templates = response.json()["templates"]
    assert len(templates) >= 5
    assert {template["id"] for template in templates} >= REQUIRED_TEMPLATE_IDS


def test_templates_include_required_display_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/templates")

    assert response.status_code == 200
    for template in response.json()["templates"]:
        assert template["name"]
        assert template["genre"]
        assert template["short_description"]
        assert template["tags"]
        assert template["recommended_tone"]


def test_templates_use_chinese_names_for_default_catalog() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/templates?locale=zh-Hans")

    assert response.status_code == 200
    names_by_id = {
        template["id"]: template["name"]
        for template in response.json()["templates"]
    }
    assert names_by_id["xianxia_rise"] == "修仙逆袭"
    assert names_by_id["apocalypse_base"] == "末世基地"


def test_storycat_prefixed_templates_return_catalog() -> None:
    client = TestClient(create_app())

    response = client.get("/storycat/v1/templates?locale=zh-Hans")

    assert response.status_code == 200
    templates = response.json()["templates"]
    assert len(templates) >= 5
    assert {template["id"] for template in templates} >= REQUIRED_TEMPLATE_IDS
