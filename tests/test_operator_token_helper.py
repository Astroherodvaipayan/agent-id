import importlib.util
from pathlib import Path
import stat

from dotenv import dotenv_values

spec = importlib.util.spec_from_file_location('operator_helper', Path(__file__).parents[1] / 'scripts' / 'set_operator_token.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_operator_token_entry_preserves_other_settings(tmp_path):
    path = tmp_path / '.env'
    path.write_text('OTHER_SETTING=kept\nOPERATOR_TOKEN=old\nexport OPERATOR_TOKEN=duplicate\n')
    helper.save_token(path, 'synthetic-${LITERAL}-token')
    values = dotenv_values(path, interpolate=False)
    assert values['OPERATOR_TOKEN'] == 'synthetic-${LITERAL}-token'
    assert values['OTHER_SETTING'] == 'kept'
    assert path.read_text().count('OPERATOR_TOKEN=') == 1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
