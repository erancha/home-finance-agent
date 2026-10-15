-- Row count of every table in the public schema, or with -v rows=1 the contents of every non-empty
-- table instead. sql-helper.sh --counts and --rows run this file.
--
-- pg_tables is read at run time, so the report follows the live schema as migrations add tables.
-- In row dumps every value is cut to 80 characters, since LangGraph's checkpoint JSON runs long,
-- and a bytea column shows only its size in bytes. \gexec runs each generated statement in turn.
\if :{?rows}
SELECT cmd
FROM (
  SELECT t.tablename, 0 AS ord, format('SELECT %L AS table_name', t.tablename) AS cmd
  FROM pg_tables t
  WHERE t.schemaname = 'public'
  UNION ALL
  SELECT t.tablename, 1 AS ord, format('SELECT %s FROM %I', cols.list, t.tablename)
  FROM pg_tables t
  JOIN LATERAL (
    SELECT string_agg(
             CASE WHEN atttypid = 'bytea'::regtype
               THEN format('octet_length(%I) AS %I', attname, attname || '_bytes')
               ELSE format('left(%I::text, 80) AS %I', attname, attname)
             END,
             ', ' ORDER BY attnum) AS list
    FROM pg_attribute
    WHERE attrelid = format('public.%I', t.tablename)::regclass AND attnum > 0 AND NOT attisdropped
  ) cols ON true
  WHERE t.schemaname = 'public'
) gen
ORDER BY tablename, ord
\gexec
\else
SELECT string_agg(
         format('SELECT %L AS table_name, count(*) AS rows FROM %I', tablename, tablename),
         E'\nUNION ALL\n' ORDER BY tablename) || E'\nORDER BY rows DESC, table_name'
FROM pg_tables
WHERE schemaname = 'public'
\gexec
\endif
