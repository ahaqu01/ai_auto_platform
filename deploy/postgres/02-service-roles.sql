-- Execute only by the migration administrator after Alembic upgrade.
DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_api') THEN
    CREATE ROLE platform_api NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_maintenance') THEN
    CREATE ROLE platform_maintenance NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('platform_api','platform_maintenance')
             AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole)) THEN
    RAISE EXCEPTION 'service roles must be restricted';
  END IF;
END
$roles$;

GRANT platform_runtime TO platform_api;
GRANT USAGE ON SCHEMA public TO platform_api, platform_maintenance;
GRANT SELECT, INSERT, UPDATE ON users TO platform_api;
REVOKE ALL ON artifact_maintenance_state FROM platform_runtime, platform_api, PUBLIC;
GRANT SELECT, INSERT, UPDATE ON artifact_maintenance_state TO platform_maintenance;
GRANT SELECT, UPDATE ON upload_sessions, artifacts TO platform_maintenance;
GRANT SELECT, INSERT ON audit_events, outbox_events TO platform_maintenance;

DROP POLICY IF EXISTS maintenance_access ON upload_sessions;
CREATE POLICY maintenance_access ON upload_sessions TO platform_maintenance
  USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS maintenance_access ON artifacts;
CREATE POLICY maintenance_access ON artifacts TO platform_maintenance
  USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS maintenance_access ON audit_events;
CREATE POLICY maintenance_access ON audit_events TO platform_maintenance
  USING (actor_type = 'SYSTEM' AND actor_id = '00000000-0000-0000-0000-000000000000'::uuid)
  WITH CHECK (actor_type = 'SYSTEM' AND actor_id = '00000000-0000-0000-0000-000000000000'::uuid);
DROP POLICY IF EXISTS maintenance_access ON outbox_events;
CREATE POLICY maintenance_access ON outbox_events TO platform_maintenance
  USING (aggregate_type = 'artifact' AND event_type IN
    ('UploadSessionExpired.v1','ArtifactDeleted.v1','ArtifactObjectMissing.v1','ArtifactOrphanDeleted.v1'))
  WITH CHECK (aggregate_type = 'artifact' AND event_type IN
    ('UploadSessionExpired.v1','ArtifactDeleted.v1','ArtifactObjectMissing.v1','ArtifactOrphanDeleted.v1'));
