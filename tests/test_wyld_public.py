import io
import json

import pytest

from app import wyld_public


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, url):
        super().__init__(json.dumps(body).encode())
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_only_three_fixed_read_operations(monkeypatch):
    monkeypatch.setenv('WYLD_API_KEY', 'test-key')
    requests = []

    def fake_open(request, timeout):
        requests.append(request)
        assert timeout == 12
        assert request.full_url.startswith(wyld_public.BASE + '/creators')
        assert request.get_header('Authorization') == 'Bearer test-key'
        if request.full_url.endswith('/creators/jane.doe'):
            body = {'data': {'username': 'jane.doe'}}
        else:
            body = {'data': {'total': 1, 'items': [{'username': 'jane.doe', 'private_email': 'omit'}]}}
        return Response(body, request.full_url)

    monkeypatch.setattr(wyld_public, '_open', fake_open)
    listed = wyld_public.list_creators(2, 5)
    profile = wyld_public.get_creator('Jane.Doe')
    found = wyld_public.search('travel', 1, 5, {'followers_min': 100})
    assert [r.get_method() for r in requests] == ['GET', 'GET', 'POST']
    assert requests[0].full_url == wyld_public.BASE + '/creators?page=2&page_size=5'
    assert requests[1].full_url == wyld_public.BASE + '/creators/jane.doe'
    assert requests[2].full_url == wyld_public.BASE + '/creators/search'
    assert json.loads(requests[2].data) == {'query': 'travel', 'page': 1, 'page_size': 5, 'filters': {'followers_min': 100}}
    assert 'private_email' not in listed['items'][0]
    assert profile['creator']['username'] == found['items'][0]['username'] == 'jane.doe'


@pytest.mark.parametrize('method,path', [
    ('DELETE', '/creators/jane'), ('PATCH', '/creators/jane'),
    ('PUT', '/creators/jane'), ('GET', '/admin'),
    ('POST', '/creators/jane'), ('GET', '/creators/../admin'),
    ('GET', '/creators/search'), ('GET', 'https://evil.test/creators'),
])
def test_forbidden_methods_paths_never_open(monkeypatch, method, path):
    monkeypatch.setenv('WYLD_API_KEY', 'test-key')
    monkeypatch.setattr(wyld_public, '_open', lambda *_args, **_kw: pytest.fail('network attempted'))
    with pytest.raises(ValueError):
        wyld_public._request(method, path)


@pytest.mark.parametrize('handle', ['../admin', 'a/b', 'a?b', 'a#b', 'search', 'a%2fb'])
def test_bad_profile_names_never_open(monkeypatch, handle):
    monkeypatch.setattr(wyld_public, '_open', lambda *_args, **_kw: pytest.fail('network attempted'))
    with pytest.raises(ValueError):
        wyld_public.get_creator(handle)


def test_bounds_and_redirect_response(monkeypatch):
    monkeypatch.setenv('WYLD_API_KEY', 'test-key')
    monkeypatch.setattr(wyld_public, '_open', lambda request, timeout: Response({'items': [], 'total': 0}, 'https://evil.test/'))
    with pytest.raises(RuntimeError, match='unavailable'):
        wyld_public.list_creators()
    with pytest.raises(ValueError):
        wyld_public.list_creators(1, 26)
    with pytest.raises(ValueError):
        wyld_public.search('query', filters={'unexpected': 1})
    assert wyld_public.NoRedirect().redirect_request(None, None, 302, 'redirect', {}, 'https://evil.test') is None


def test_credential_reflection_and_invalid_schema_are_private(monkeypatch):
    monkeypatch.setenv('WYLD_API_KEY', 'test-key')
    monkeypatch.setattr(wyld_public, '_open', lambda request, timeout: Response({'data': {'total': 1, 'items': [{'username': 'jane', 'full_name': 'test-key'}]}}, request.full_url))
    with pytest.raises(RuntimeError) as caught:
        wyld_public.list_creators()
    assert 'test-key' not in str(caught.value)
    monkeypatch.setattr(wyld_public, '_open', lambda request, timeout: Response({'unknown': []}, request.full_url))
    with pytest.raises(RuntimeError, match='unsupported or invalid creator schema'):
        wyld_public.list_creators()


def test_provider_engagement_above_100_is_kept_as_raw_bounded_value():
    record = wyld_public.profile_fields({'username': 'creator', 'engagement_rate': 120.5})
    assert record['engagement_rate'] == 120.5
    with pytest.raises(ValueError):
        wyld_public.profile_fields({'username': 'creator', 'engagement_rate': 10001})
    with pytest.raises(ValueError):
        wyld_public.profile_fields({'username': 'creator', 'fit_score': 101})
