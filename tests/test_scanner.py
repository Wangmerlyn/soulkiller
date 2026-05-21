from soulkiller.scanner import scan_tree


def test_scan_tree_rejects_secret_filename(tmp_path):
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("auth.json" in issue.path for issue in result.issues)


def test_scan_tree_rejects_env_variant_filename(tmp_path):
    (tmp_path / ".env.local").write_text("OPENAI_API_KEY=abc123456789\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any(".env.local" in issue.path for issue in result.issues)


def test_scan_tree_rejects_secret_content(tmp_path):
    file_path = tmp_path / "note.md"
    file_path.write_text("api_key = 'abc123'\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("api_key" in issue.message for issue in result.issues)


def test_scan_tree_rejects_prefixed_api_key_assignment(tmp_path):
    file_path = tmp_path / "note.md"
    file_path.write_text("OPENAI_API_KEY=sk-abc123456789\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("OPENAI_API_KEY" in issue.message for issue in result.issues)


def test_scan_tree_allows_redacted_secret_reference(tmp_path):
    file_path = tmp_path / "memory.md"
    file_path.write_text("mount options included secret=[REDACTED_SECRET]\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert result.ok


def test_scan_tree_allows_environment_token_lookup_code(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text(
        "self.access_token = os.environ.get(ENV_ACCESS_TOKEN)\n"
        'headers = {"x-yunxiao-token": self.access_token}\n',
        encoding="utf-8",
    )

    result = scan_tree(tmp_path)

    assert result.ok


def test_scan_tree_allows_environment_variable_name_constant(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text(
        'ENV_ACCESS_TOKEN = "YUNXIAO_ACCESS_TOKEN"\n'
        "token = os.environ.get(ENV_ACCESS_TOKEN)\n",
        encoding="utf-8",
    )

    result = scan_tree(tmp_path)

    assert result.ok


def test_scan_tree_rejects_unused_environment_variable_name_constant(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text('ENV_ACCESS_TOKEN = "YUNXIAO_ACCESS_TOKEN"\n', encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("ENV_ACCESS_TOKEN" in issue.message for issue in result.issues)


def test_scan_tree_rejects_lowercase_environment_variable_name_constant(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text('env_access_token = "YUNXIAO_ACCESS_TOKEN"\n', encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("env_access_token" in issue.message for issue in result.issues)


def test_scan_tree_allows_documented_placeholder_secret_value(tmp_path):
    file_path = tmp_path / "SKILL.md"
    file_path.write_text('export YUNXIAO_ACCESS_TOKEN="你的个人访问令牌"\n', encoding="utf-8")

    result = scan_tree(tmp_path)

    assert result.ok


def test_scan_tree_rejects_non_ascii_password_value(tmp_path):
    file_path = tmp_path / "note.md"
    file_path.write_text('PASSWORD="pässwörd"\n', encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("PASSWORD" in issue.message for issue in result.issues)


def test_scan_tree_rejects_non_ascii_secret_value(tmp_path):
    file_path = tmp_path / "note.md"
    file_path.write_text('MY_SECRET="真实密钥"\n', encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("MY_SECRET" in issue.message for issue in result.issues)


def test_scan_tree_rejects_uppercase_secret_value(tmp_path):
    file_path = tmp_path / "note.md"
    file_path.write_text('MY_SECRET="PRODSECRET123"\n', encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("MY_SECRET" in issue.message for issue in result.issues)


def test_scan_tree_rejects_uppercase_password_value(tmp_path):
    file_path = tmp_path / "note.md"
    file_path.write_text('PASSWORD="ROOTPASSWORD"\n', encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("PASSWORD" in issue.message for issue in result.issues)


def test_scan_tree_rejects_uppercase_secret_value_under_env_constant_key(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text(
        'ENV_ACCESS_TOKEN = "ROOTPASSWORD"\n'
        "token = os.environ.get(ENV_ACCESS_TOKEN)\n",
        encoding="utf-8",
    )

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("ENV_ACCESS_TOKEN" in issue.message for issue in result.issues)


def test_scan_tree_rejects_mismatched_env_name_constant_value(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text(
        'ENV_API_KEY = "PROD_SECRET_KEY"\n'
        "api_key = os.environ.get(ENV_API_KEY)\n",
        encoding="utf-8",
    )

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("ENV_API_KEY" in issue.message for issue in result.issues)


def test_scan_tree_rejects_ambiguous_env_password_constant_value(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text(
        'ENV_PASSWORD = "ROOT_PASSWORD"\n'
        "password = os.environ.get(ENV_PASSWORD)\n",
        encoding="utf-8",
    )

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("ENV_PASSWORD" in issue.message for issue in result.issues)


def test_scan_tree_rejects_generic_env_access_token_name(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text(
        'ENV_ACCESS_TOKEN = "ROOT_ACCESS_TOKEN"\n'
        "token = os.environ.get(ENV_ACCESS_TOKEN)\n",
        encoding="utf-8",
    )

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("ENV_ACCESS_TOKEN" in issue.message for issue in result.issues)


def test_scan_tree_rejects_generic_env_api_key_name(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text(
        'ENV_API_KEY = "PROD_SECRET_API_KEY"\n'
        "api_key = os.environ.get(ENV_API_KEY)\n",
        encoding="utf-8",
    )

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("ENV_API_KEY" in issue.message for issue in result.issues)


def test_scan_tree_does_not_cross_lines_when_checking_assignments(tmp_path):
    file_path = tmp_path / "client.py"
    file_path.write_text(
        "if not self.access_token:\n"
        '    raise ValueError("Environment variable TOKEN is not set")\n',
        encoding="utf-8",
    )

    result = scan_tree(tmp_path)

    assert result.ok


def test_scan_tree_allows_ellipsis_placeholder_values(tmp_path):
    file_path = tmp_path / "review.md"
    file_path.write_text("The example had `api_key: ... llm_provider: openai`.\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert result.ok


def test_scan_tree_rejects_binary_file(tmp_path):
    file_path = tmp_path / "memory.bin"
    file_path.write_bytes(b"\x00\x01\x02")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("binary" in issue.message for issue in result.issues)


def test_scan_tree_allows_plain_memory_text(tmp_path):
    file_path = tmp_path / "MEMORY.md"
    file_path.write_text("remember this workflow preference\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert result.ok
