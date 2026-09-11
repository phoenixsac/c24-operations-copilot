-- Row-level security. docs/DOMAIN_v2.md §6, docs/INVARIANTS.md E3 / H10.
--
-- The central claim of the design is that trust boundaries live in the data
-- layer. This file is that claim.
--
-- Shape of every policy:
--   own city always
--   OR own region when the caller is a supervisor
--
-- A forgotten repository filter now returns zero rows instead of everyone's
-- rows: the failure mode inverts from silent leak to obvious break.

-- Reference data an agent must read regardless of who owns the row.
GRANT USAGE ON SCHEMA public TO app_user, app_readonly;

GRANT SELECT, INSERT, UPDATE ON
  customer, vehicle, orders, payment, refund, rc_case, refurb_job,
  delivery, ticket, ticket_message, conversation, conversation_turn
TO app_user;

-- DELETE, granted on exactly two tables and no others.
--
-- A conversation is the operator's own working notes, and notes nobody can
-- clear are notes people avoid making. Deleting one destroys no record of
-- anything that was *done*: `action_audit` is a different table, append-only,
-- and every proposal, approval and execution survives with its actor and
-- idempotency key. The turns cascade from the parent row.
--
-- Note what is deliberately absent from this grant: every other table.
GRANT DELETE ON conversation, conversation_turn TO app_user;

-- Append-only tables: insert and read, never update or delete. A4.
GRANT SELECT, INSERT ON order_event, action_audit TO app_user;

GRANT SELECT ON app_actor TO app_user, app_readonly;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- The query console. SELECT only, and only on tables a supervisor could
-- already read through the API. E7.
GRANT SELECT ON
  customer, vehicle, orders, order_event, payment, refund, rc_case,
  refurb_job, delivery, ticket
TO app_readonly;

-- ---------------------------------------------------------------------------
-- Policies
-- ---------------------------------------------------------------------------

DO $$
DECLARE
  t TEXT;
  scoped TEXT[] := ARRAY[
    'customer', 'vehicle', 'orders', 'order_event', 'payment', 'refund',
    'rc_case', 'refurb_job', 'delivery', 'ticket', 'ticket_message',
    'action_audit', 'conversation', 'conversation_turn'
  ];
BEGIN
  FOREACH t IN ARRAY scoped LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    -- FORCE so that even a table owner is subject to the policy. Superusers
    -- still bypass, which is why the app never connects as one.
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);

    EXECUTE format($f$
      CREATE POLICY city_scope ON %I
        FOR ALL
        USING (
          city_code = current_setting('app.city_code', true)
          OR (current_setting('app.role', true) = 'supervisor'
              AND region = current_setting('app.region', true))
        )
        WITH CHECK (
          city_code = current_setting('app.city_code', true)
          OR (current_setting('app.role', true) = 'supervisor'
              AND region = current_setting('app.region', true))
        )
    $f$, t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- The isolation test, as an assertion rather than prose
-- ---------------------------------------------------------------------------
--
-- Run against a scoped connection, raw and unrestricted:
--
--   SET LOCAL app.city_code = 'mum';
--   SET LOCAL app.role      = 'l1_agent';
--   SELECT count(*) FROM ticket WHERE city_code <> 'mum';   -- must be 0
--
-- Three lines, and they are what turn "trust boundaries live in the database"
-- from an assertion into something falsifiable. docs/SCOPE.md §1.

CREATE OR REPLACE FUNCTION assert_rls_isolation()
RETURNS TABLE (check_name TEXT, foreign_rows BIGINT, passed BOOLEAN)
LANGUAGE sql SECURITY INVOKER AS $$
  SELECT 'ticket rows outside city scope',
         count(*),
         count(*) = 0
  FROM ticket
  WHERE city_code <> current_setting('app.city_code', true)
  UNION ALL
  SELECT 'order rows outside city scope',
         count(*),
         count(*) = 0
  FROM orders
  WHERE city_code <> current_setting('app.city_code', true)
  UNION ALL
  SELECT 'ticket_message rows outside city scope',
         count(*),
         count(*) = 0
  FROM ticket_message
  WHERE city_code <> current_setting('app.city_code', true);
$$;

GRANT EXECUTE ON FUNCTION assert_rls_isolation() TO app_user, app_readonly;
