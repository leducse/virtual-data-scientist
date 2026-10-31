# Sales Analytics Model Registry POC Plan

1. ✅ **Define the deal-risk use case** — Fix the user, prediction horizon,
   feature boundary, prohibited use, and measurable success tenets.
   - Output: `model_registry/specs/deal_risk_use_case_spec.md`
2. ✅ **Build the evaluation substrate** — Generate deterministic synthetic
   weekly snapshots, validate the feature contract, and split chronologically.
3. ✅ **Measure a simple baseline** — Compare constant-risk and transparent
   logistic-regression models on calibration, average precision, and recall at
   review capacity.
4. ✅ **Add the local registry lifecycle** — Persist versioned model cards,
   artifacts, metrics, gates, approval state, lineage, and audit events.
5. ✅ **Add governed batch scoring** — Require an approved version and return
   risk scores, reason codes, contract version, and model lineage.
6. ✅ **Integrate the existing VDS UI/API** — Expose catalog, train, approve, and
   score actions without adding another application shell.
7. ✅ **Validate and document** — Run unit/browser checks, update architecture and
   project context, and record the decision gate before any complex tuning.

Validation completed July 19, 2026: 15 automated tests passed; JavaScript and
Python syntax checks passed; the browser workflow completed evaluate → review →
approve → batch score at a 390 px viewport with no horizontal overflow.

## Decision gate

The POC stops after the baseline and registry workflow. Gradient boosting,
transformer routing, SageMaker training, and production data remain unapproved
future experiments until the fixed evidence is reviewed.
