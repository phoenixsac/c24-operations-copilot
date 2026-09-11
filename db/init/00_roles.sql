-- Roles. docs/DESIGN.md §7.
--
-- Three roles, and the split matters: RLS is bypassed by table owners and by
-- superusers, so if the application connected as the owner every isolation test
-- would pass for the wrong reason. app_user owns nothing.

-- Application connection. RLS applies. Not the table owner.
CREATE ROLE app_user LOGIN PASSWORD 'app_user' NOBYPASSRLS;

-- Query console. SELECT only, capped, timed out. docs/INVARIANTS.md E7.
CREATE ROLE app_readonly LOGIN PASSWORD 'app_readonly' NOBYPASSRLS;

-- Migrations only. Never used at runtime.
CREATE ROLE app_migrator LOGIN PASSWORD 'app_migrator' NOBYPASSRLS;

-- The console cannot outrun its budget even if a supervisor writes a bad join.
ALTER ROLE app_readonly SET statement_timeout = '5s';
ALTER ROLE app_user     SET statement_timeout = '10s';

-- Defaults for the session variables the policies read. Without these a
-- connection that forgets to SET LOCAL errors instead of silently matching, and
-- an empty string matches no row — which is the failure direction we want.
ALTER ROLE app_user     SET app.city_code = '';
ALTER ROLE app_user     SET app.region    = '';
ALTER ROLE app_user     SET app.role      = '';
ALTER ROLE app_readonly SET app.city_code = '';
ALTER ROLE app_readonly SET app.region    = '';
ALTER ROLE app_readonly SET app.role      = '';
