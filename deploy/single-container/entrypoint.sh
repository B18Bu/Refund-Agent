#!/bin/sh
set -eu
PGDATA=${PGDATA:-/var/lib/postgresql/data}
POSTGRES_DB=${POSTGRES_DB:-refund}
mkdir -p "$PGDATA" /var/lib/redis /data/uploads
chown -R postgres:postgres "$PGDATA"
chown -R redis:redis /var/lib/redis
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  runuser -u postgres -- initdb -D "$PGDATA"
fi
runuser -u postgres -- pg_ctl -D "$PGDATA" -o "-c max_connections=200" -w start
until runuser -u postgres -- pg_isready -d postgres >/dev/null 2>&1; do
  sleep 1
done
if ! runuser -u postgres -- psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$POSTGRES_DB'" | grep -q 1; then
  runuser -u postgres -- createdb "$POSTGRES_DB"
fi
for migration in 20260829_create_core_users_tickets.sql 20260830_add_agent_evaluation_runs.sql 20260831_add_tickets_trace_id.sql 20260831_add_evidence_audit.sql 20260903_add_commerce.sql 20260904_add_customer_role.sql 20260904_add_catalog_state.sql 20260906_add_rag_knowledge.sql 20260907_add_customer_assistant.sql 20260908_add_customer_support.sql 20260909_add_product_category.sql; do
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d "$POSTGRES_DB" -f "/app/migrations/$migration"
done
runuser -u postgres -- pg_ctl -D "$PGDATA" -m fast -w stop
exec supervisord -n -c /etc/supervisor/conf.d/app.conf
