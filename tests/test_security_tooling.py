"""Safety guards for load/DAST/DR tooling."""
from pathlib import Path


def test_active_security_tools_require_explicit_staging_flags():
    for name, flag in [
        ("load/run-load-suite.sh", "ALLOW_LOAD_TEST"),
        ("load/redis-outage-drill.sh", "ALLOW_CHAOS_TEST"),
        ("security/run-zap.sh", "ALLOW_DAST"),
    ]:
        text = Path(name).read_text()
        assert flag in text and "TARGET_ENV" in text and "staging" in text
        assert "Refusing production" in text


def test_restore_drill_refuses_production_target():
    text = Path("deploy/restore-drill.sh").read_text()
    assert '"$DATABASE_URL" == "$RESTORE_DATABASE_URL"' in text
    assert "REFUSING" in text


def test_load_scenarios_have_thresholds():
    scripts = list(Path("load/k6").glob("*.js"))
    assert len(scripts) >= 3
    assert all("thresholds" in script.read_text() for script in scripts)
