from fastapi.testclient import TestClient

from app.api import app


def test_creator_demo_is_public_local_simulation():
    response = TestClient(app).get('/creator-demo')
    assert response.status_code == 200
    assert 'Creator agent' in response.text
    assert 'Your decision desk' in response.text
    assert 'Simulate send' in response.text
    assert 'No email, provider, model, or agent service is called.' in response.text
