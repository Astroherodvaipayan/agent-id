from pathlib import Path

from dotenv import dotenv_values

from scripts.setup_local import configure


def test_wizard_prompts_only_missing_values_and_never_prints_them(tmp_path):
    path = tmp_path / '.env'
    path.write_text('OPERATOR_TOKEN="existing-token"\nSMTP_HOST=custom.smtp.test\nOTHER_SETTING=kept\n')
    prompts = []
    answers = iter(['synthetic-${LITERAL}-wyld', 'synthetic-mail-pass'])
    output = []

    def hidden(prompt):
        prompts.append(prompt)
        return next(answers)

    configure(path, hidden_input=hidden, output=output.append)
    values = dotenv_values(path, interpolate=False)
    assert len(prompts) == 2
    assert values['OPERATOR_TOKEN'] == 'existing-token'
    assert values['WYLD_API_KEY'] == 'synthetic-${LITERAL}-wyld'
    assert values['WYLD_PROVIDER'] == 'public'
    assert values['SMTP_PASSWORD'] == values['IMAP_PASSWORD'] == 'synthetic-mail-pass'
    assert values['SMTP_HOST'] == 'custom.smtp.test'
    assert values['OTHER_SETTING'] == 'kept'
    assert 'synthetic-' not in '\n'.join(output)
    configure(path, hidden_input=lambda _: (_ for _ in ()).throw(AssertionError('unexpected prompt')), output=output.append)


def test_wizard_refuses_symlink(tmp_path):
    source = tmp_path / 'source'
    source.write_text('')
    link = tmp_path / '.env'
    link.symlink_to(source)
    try:
        configure(link, hidden_input=lambda _: 'unused', output=lambda _: None)
    except ValueError:
        pass
    else:
        raise AssertionError('symlink accepted')
