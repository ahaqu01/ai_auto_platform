"""M1-09 tenant RLS and runtime role separation."""

from alembic import op

revision = "20260827_07"
down_revision = "20260827_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $check$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles runtime
            WHERE runtime.rolname = 'platform_runtime'
              AND NOT runtime.rolsuper
              AND NOT runtime.rolbypassrls
              AND NOT runtime.rolcreaterole
          ) THEN
            RAISE EXCEPTION 'platform_runtime must be provisioned as a restricted role';
          END IF;
          IF NOT pg_has_role(CURRENT_USER, 'platform_runtime', 'MEMBER') THEN
            RAISE EXCEPTION 'database owner must be a platform_runtime member';
          END IF;
        END
        $check$;
        """
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          EXECUTE format('GRANT USAGE ON SCHEMA %I TO platform_runtime', current_schema());
          EXECUTE format(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO platform_runtime',
            current_schema()
          );
        END
        $grant$;
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
        "users, organizations, organization_members, organization_invites, "
        "projects, project_members, audit_events, idempotency_records, outbox_events "
        "TO platform_runtime"
    )
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON organizations
        USING (
          id = NULLIF(current_setting('app.organization_id', true), '')::uuid
          OR (
            NULLIF(current_setting('app.organization_id', true), '')::uuid IS NULL
            AND EXISTS (
              SELECT 1 FROM organization_members membership
              WHERE membership.organization_id = organizations.id
                AND membership.user_id =
                  NULLIF(current_setting('app.actor_id', true), '')::uuid
            )
          )
        )
        WITH CHECK (
          id = NULLIF(current_setting('app.organization_id', true), '')::uuid
        )
        """
    )
    op.execute("ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON organization_members
        USING (
          organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
          OR (
            NULLIF(current_setting('app.organization_id', true), '')::uuid IS NULL
            AND user_id = NULLIF(current_setting('app.actor_id', true), '')::uuid
          )
        )
        WITH CHECK (
          organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
        )
        """
    )
    op.execute("ALTER TABLE organization_invites ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON organization_invites "
        "USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )
    op.execute("ALTER TABLE projects ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON projects "
        "USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )
    op.execute("ALTER TABLE project_members ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON project_members "
        "USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_events "
        "USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )
    op.execute("ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON outbox_events "
        "USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )
    op.execute(
        """
        CREATE FUNCTION resolve_invite_organization(p_token_hash bytea)
        RETURNS uuid LANGUAGE sql SECURITY DEFINER STABLE
        SET search_path FROM CURRENT
        AS $function$
          SELECT organization_id FROM organization_invites WHERE token_hash = p_token_hash
        $function$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION resolve_invite_organization(bytea) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION resolve_invite_organization(bytea) TO platform_runtime"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_invite_organization(bytea)")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON outbox_events")
    op.execute("ALTER TABLE outbox_events DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_events")
    op.execute("ALTER TABLE audit_events DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON project_members")
    op.execute("ALTER TABLE project_members DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON projects")
    op.execute("ALTER TABLE projects DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON organization_invites")
    op.execute("ALTER TABLE organization_invites DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON organization_members")
    op.execute("ALTER TABLE organization_members DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON organizations")
    op.execute("ALTER TABLE organizations DISABLE ROW LEVEL SECURITY")
    op.execute(
        "REVOKE ALL ON TABLE users, organizations, organization_members, "
        "organization_invites, projects, project_members, audit_events, "
        "idempotency_records, outbox_events FROM platform_runtime"
    )
    op.execute(
        """
        DO $revoke$
        BEGIN
          EXECUTE format(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM platform_runtime',
            current_schema()
          );
          EXECUTE format('REVOKE USAGE ON SCHEMA %I FROM platform_runtime', current_schema());
        END
        $revoke$;
        """
    )
