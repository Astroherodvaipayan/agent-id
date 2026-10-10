import importlib.util
from pathlib import Path
import stat
from dotenv import dotenv_values

spec = importlib.util.spec_from_file_location('email_helper', Path(__file__).parents[1] / 'scripts' / 'set_email_password.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_local_save_preserves_other_settings_and_permissions(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# Preserve comment\nSMTP_HOST=host.test\nOTHER_SETTING=kept\nSMTP_PASSWORD=old\nexport IMAP_PASSWORD=old\nSMTP_PASSWORD=duplicate\n')
    helper.save_password(path, 'isolated"test\\value')
    values = dotenv_values(path)
    assert values['SMTP_PASSWORD'] == values['IMAP_PASSWORD'] == 'isolated"test\\value'
    assert values['OTHER_SETTING'] == 'kept' and values['SMTP_HOST'] == 'host.test'
    assert values['SMTP_PORT'] == '587'
    assert values['SMTP_USERNAME'] == 'krishnadvaipayana2003@gmail.com'
    assert values['IMAP_HOST'] == 'imap.gmail.com'
    assert values['IMAP_PORT'] == '993'
    assert '# Preserve comment' in path.read_text()
    assert path.read_text().count('SMTP_PASSWORD=') == 1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_readiness_prints_flags_only(tmp_path, capsys):
    path = tmp_path / '.env'
    helper.save_password(path, 'isolated-test-value')
    helper.readiness(path)
    output = capsys.readouterr().out
    assert 'isolated-test-value' not in output
    assert 'SMTP_PASSWORD configured: yes' in output
    assert 'IMAP_HOST configured: yes' in output
