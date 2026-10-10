import os

from app.local_config import load_local_config


def test_local_config_loads_synthetic_values_without_overriding_process(monkeypatch, tmp_path):
    path = tmp_path / '.env'
    path.write_text('WYLD_PROVIDER=public\nWYLD_API_KEY="synthetic-${LITERAL}-key"\nOPERATOR_TOKEN=file-token\nUNRELATED_CONFIG=ignored\n')
    original = {name: os.environ.get(name) for name in ('WYLD_PROVIDER', 'WYLD_API_KEY', 'OPERATOR_TOKEN', 'UNRELATED_CONFIG')}
    try:
        monkeypatch.delenv('WYLD_PROVIDER', raising=False)
        monkeypatch.delenv('WYLD_API_KEY', raising=False)
        monkeypatch.delenv('UNRELATED_CONFIG', raising=False)
        monkeypatch.setenv('OPERATOR_TOKEN', 'process-token')
        assert load_local_config(path)
        assert os.getenv('WYLD_PROVIDER') == 'public'
        assert os.getenv('WYLD_API_KEY') == 'synthetic-${LITERAL}-key'
        assert os.getenv('OPERATOR_TOKEN') == 'process-token'
        assert os.getenv('UNRELATED_CONFIG') is None
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_local_config_refuses_symlink(monkeypatch, tmp_path):
    source = tmp_path / 'source'
    source.write_text('WYLD_API_KEY=synthetic-test-key\n')
    link = tmp_path / '.env'
    link.symlink_to(source)
    monkeypatch.delenv('WYLD_API_KEY', raising=False)
    assert not load_local_config(link)
    assert os.getenv('WYLD_API_KEY') is None
