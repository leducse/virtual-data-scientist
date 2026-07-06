# Productionization Plan

The local POC proves the report-building loop. The next phase should improve
governance and repeatability rather than adding more chart types.

## Target Slice

Move from a single-session demo toward a governed internal reporting platform:

```text
data source metadata
-> secret boundary
-> schema snapshot
-> SQL block generation and preview
-> audit event
-> report version
-> published report with lineage
```

## Recommended Build Order

1. Data-source metadata without raw secrets
   - Persist data source name, type, host alias, database, default schema, and
     read-only status.
   - Store only a secret reference, not passwords or access keys.
   - Keep the local demo path working with SQLite and in-memory Postgres configs.

2. Secret boundary
   - Local mode: in-memory secret reference or ignored local config.
   - AWS mode: Secrets Manager reference.
   - Never persist browser-submitted passwords to disk.

3. Audit events
   - Record data-source creation/test events.
   - Record generated SQL block preview events.
   - Record publish events with report id, version, parameters, and source ids.

4. Report versions
   - Separate draft report id from immutable published versions.
   - Store SQL block text, parameters, visual config, and template id per version.
   - Add rollback by republishing a prior version later.

5. Lineage display
   - For each published report, show data source, tables/columns used, SQL block
     names, last preview time, and refresh mode.

## Non-Goals For This Slice

- Full semantic model.
- Multi-tenant auth.
- Arbitrary Python transforms.
- Write-capable database credentials.
- Athena/Glue automation until the governed Postgres/SQLite loop is clean.

## Validation

Safe local validation:

```bash
python3 server.py
```

Browser workflow to verify:

```text
open workbench
inspect demo schema
generate report
preview each SQL block
publish report
open published URL
```

Unit-test targets to add with code changes:

- SQL validation rejects non-SELECT statements.
- Parameter binding never string-concatenates user values.
- Data-source metadata persistence excludes raw secrets.
- Publish creates immutable version records.
- Audit events are written for preview and publish.

## Sensitive Boundaries

- Do not store raw Postgres passwords.
- Do not connect to production databases from the POC.
- Do not add write-capable database actions.
- Do not use Bedrock unless credentials and model id are explicitly configured.
