import subprocess


def test_source_wrapper_runs_help():
    result = subprocess.run(["bin/soulkiller", "--help"], text=True, capture_output=True)

    assert result.returncode == 0
    assert "usage: soulkiller" in result.stdout
