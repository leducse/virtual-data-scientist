# Deal Risk Model Registry Use Case

## Business Problem

Sales-operations analysts need a governed way to evaluate, register, approve,
and batch-score weekly opportunity snapshots for the risk that an open deal will
be lost or slip more than 30 days within the next 30 days. The first POC uses
synthetic data and a transparent logistic-regression baseline; it does not make
personnel decisions or connect to production warehouse data.

## Primary Users

Sales-operations analysts, data scientists, analytics engineers, model reviewers

## Success Tenets

- **Point-in-time validity** — Every feature is available at the snapshot time,
  train/test partitions are chronological, and forbidden post-outcome fields are
  rejected.
- **Baseline value** — The candidate improves Brier score and average precision
  over a constant-risk baseline and reports recall at the team's review capacity.
- **Governed reuse** — Every scoring result names an approved model version,
  feature-contract version, evaluation metrics, reason codes, and audit event.
