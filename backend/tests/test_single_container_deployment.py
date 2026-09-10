from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose" / "docker-compose.yml"
NGINX = ROOT / "frontend" / "nginx.conf"
ENTRYPOINT = ROOT / "deploy" / "single-container" / "entrypoint.sh"
SUPERVISOR = ROOT / "deploy" / "single-container" / "supervisord.conf"
DOCKERFILE = ROOT / "deploy" / "single-container" / "Dockerfile"


def test_compose_defines_only_one_application_service():
    content = COMPOSE.read_text(encoding="utf-8")

    assert "  app:\n" in content
    assert "  postgres:\n" not in content
    assert "  redis:\n" not in content
    assert "socket_timeout=10" in content


def test_nginx_proxies_api_to_the_same_container():
    content = NGINX.read_text(encoding="utf-8")

    assert "location /api/" in content
    assert "location = /healthz" in content
    assert "proxy_pass http://127.0.0.1:8000;" in content


def test_entrypoint_runs_migrations_after_database_readiness():
    content = ENTRYPOINT.read_text(encoding="utf-8")

    assert content.index("pg_isready") < content.index("20260829_create_core_users_tickets.sql")


def test_entrypoint_uses_lf_line_endings_for_linux_execution():
    assert b"\r\n" not in ENTRYPOINT.read_bytes()


def test_entrypoint_runs_all_migrations_in_version_order():
    content = ENTRYPOINT.read_text(encoding="utf-8")
    migrations = (
        "20260829_create_core_users_tickets.sql",
        "20260830_add_agent_evaluation_runs.sql",
        "20260831_add_tickets_trace_id.sql",
        "20260831_add_evidence_audit.sql",
        "20260903_add_commerce.sql",
        "20260904_add_customer_role.sql",
        "20260904_add_catalog_state.sql",
        "20260906_add_rag_knowledge.sql",
        "20260907_add_customer_assistant.sql",
    )

    positions = [content.index(migration) for migration in migrations]
    assert positions == sorted(positions)


def test_supervisor_manages_all_long_running_processes():
    content = SUPERVISOR.read_text(encoding="utf-8")

    assert "file=/tmp/supervisor.sock" in content
    assert "serverurl=unix:///tmp/supervisor.sock" in content
    assert "[rpcinterface:supervisor]" in content
    assert "stdout_logfile_maxbytes=0" in content
    assert "stderr_logfile_maxbytes=0" in content
    for program in ("postgres", "redis", "rag-embedding", "api", "worker", "catalog-worker", "nginx"):
        assert f"[program:{program}]" in content


def test_supervisor_uses_redis_stack_for_redis_checkpointer_compatibility():
    assert "/opt/redis-stack/bin/redis-stack-server" in SUPERVISOR.read_text(encoding="utf-8")


def test_dockerfile_resumes_and_verifies_pytorch_cpu_wheel_download():
    content = DOCKERFILE.read_text(encoding="utf-8")

    assert "rm -f /etc/nginx/sites-enabled/default" in content
    assert "curl --fail --location --retry 10 --retry-all-errors --continue-at -" in content
    assert "sha256sum -c" in content
    assert "torch-2.6.0%2Bcpu-cp311-cp311-linux_x86_64.whl" in content
    assert "/tmp/torch-2.6.0+cpu-cp311-cp311-linux_x86_64.whl" in content
    assert "--timeout 60" in content
    assert "--mount=type=cache,target=/root/.cache/pip" in content
    assert "PIP_NO_CACHE_DIR" not in content


def test_dockerfile_includes_security_test_resources():
    content = DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY scripts ./scripts" in content
    assert "COPY evals ./evals" in content
    assert "COPY deploy /deploy" in content
    assert "COPY scripts /scripts" in content
    assert "COPY evals /evals" in content
    assert "COPY frontend/nginx.conf /frontend/nginx.conf" in content


def test_compose_keeps_evaluation_artifacts_writable_for_security_reports():
    content = COMPOSE.read_text(encoding="utf-8")

    assert "../../artifacts:/app/artifacts:ro" not in content
    assert "../../artifacts:/app/artifacts" in content
