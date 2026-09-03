from aida_sidecar.security import validate_python


def test_allows_analysis_libraries() -> None:
    assert validate_python("import pandas as pd\nresult = pd.Series([1, 2]).mean()") == []


def test_blocks_system_and_network_escape_hatches() -> None:
    issues = validate_python("import os\nos.system('whoami')")
    assert any("Import is not allowed" in issue for issue in issues)
    assert any("system" in issue for issue in issues)

