import importlib.util
import json
from pathlib import Path

from app.models import Decision, Role, Ticket, TicketStatus, User


def test_build_summary_uses_json_reports_and_redacts_runtime_events(tmp_path, db_session):
    from app.security.governance import build_summary

    owner = User(username="governance-owner", password_hash="x", role=Role.CS)
    db_session.add(owner)
    db_session.flush()
    db_session.add(
        Ticket(
            ticket_no="security-ticket",
            user_id=owner.id,
            amount=128,
            image_paths=[],
            status=TicketStatus.SUSPENDED,
            decision=Decision.PENDING,
            decision_reasons=["security_injection_detected"],
            evidence_audit={"security": {"risk": 1.0, "flags": ["dangerous_tool"]}},
            ocr_text="13812340000 sk-secret-never-return",
        )
    )
    db_session.commit()
    report = tmp_path / "red-blue.json"
    report.write_text(
        '{"generated_at":"2026-09-01T00:00:00Z","attack_count":100,"block_rate":0.98,"categories":[]}',
        encoding="utf-8",
    )

    summary = build_summary(
        db_session,
        red_blue_path=report,
        dlp_path=tmp_path / "missing.json",
        audit_path=tmp_path / "missing-audit.json",
    )

    assert summary["red_blue"]["attack_count"] == 100
    assert summary["runtime"]["pending_human_review"] == 1
    assert summary["runtime"]["recent_events"][0]["flags"] == ["dangerous_tool"]
    assert "13812340000" not in str(summary)
    assert "sk-secret-never-return" not in str(summary)


def test_red_blue_report_uses_only_failed_sample_ids(tmp_path, monkeypatch):
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_red_blue_test.py"
    spec = importlib.util.spec_from_file_location("security_red_blue", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)

    report = module.run()

    persisted = json.loads(
        (tmp_path / "artifacts" / "security-red-blue-report.json").read_text(encoding="utf-8")
    )
    assert report["failed_sample_ids"] == persisted["failed_sample_ids"]
    assert "text" not in str(persisted)


def test_security_audit_ignores_shell_true_text_but_finds_executable_code(tmp_path, monkeypatch):
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_security_audit.py"
    spec = importlib.util.spec_from_file_location("security_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    (tmp_path / "backend").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "documented.py").write_text(
        '"""固定参数执行，禁止 shell=True。"""\n', encoding="utf-8"
    )
    (tmp_path / "backend" / "unsafe.py").write_text(
        "subprocess.run(['echo', 'x'], shell=True)\n", encoding="utf-8"
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    report = module.run()

    assert report["finding_counts"]["shell_true"] == 1
