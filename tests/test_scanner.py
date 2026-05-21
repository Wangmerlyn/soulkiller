from soulkiller.scanner import scan_tree


def test_scan_tree_rejects_secret_filename(tmp_path):
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("auth.json" in issue.path for issue in result.issues)


def test_scan_tree_rejects_secret_content(tmp_path):
    file_path = tmp_path / "note.md"
    file_path.write_text("api_key = 'abc123'\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("api_key" in issue.message for issue in result.issues)


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
