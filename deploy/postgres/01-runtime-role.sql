\set ON_ERROR_STOP on

DO $role$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_runtime') THEN
    CREATE ROLE platform_runtime
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$role$;

DO $membership$
DECLARE
  owner_name text;
BEGIN
  FOREACH owner_name IN ARRAY ARRAY['platform', 'platform_test']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = owner_name) THEN
      EXECUTE format('GRANT platform_runtime TO %I', owner_name);
    END IF;
  END LOOP;
END
$membership$;
