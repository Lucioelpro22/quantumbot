# Offline engineering runner: proposal requiring independent review

Date: 2026-10-05. Status: DRAFT, activation BLOCKED.

The current hosted job fails with `OFFLINE_DEPENDENCY_MISSING:pytest` because
`python -I` cannot see the required preinstalled distribution. The existing
checker is behaving as designed. Installing packages in that check would violate
[the admission directive](OPERATIONAL_PRECOMMIT_CI_DIRECTIVE.md), rule 5.

The proposed workflow uses a disposable container with an independently approved
immutable image digest. It accepts only
`ghcr.io/lucioelpro22/quantumbot-engineering@sha256:<64 lowercase hex digits>`
from administrative variable `OPERATIONAL_ENGINEERING_IMAGE`. There is no default,
mutable-tag fallback, package installation, image build, publication or persistent
runner in the admission job. Docker capabilities are dropped and gaining new
privileges is denied. This does not claim a global network/process sandbox: the
trusted checkout and bounded GitHub metadata request still need network access.

The image must contain Python 3.14, pytest **9.1.1**, jsonschema **4.26.0**, Git,
and the compatible runtime/system libraries needed by the existing pinned
checkout action. Dependencies must be visible under `python -I`; user-site or
`PYTHONPATH` installations are insufficient. The new preflight verifies isolated
Python and distribution versions before acquiring repository code. The original
checker independently checks exact dependencies again. Candidate tree equality,
trusted checkout SHA, token permissions and expected confirmed-exposure failure
semantics remain intact.

## Review and activation procedure

1. Review `SPEC-ENGINEERING-OFFLINE-RUNNER-001` and this exact workflow change.
   The SPEC is DRAFT; the implementing agent does not approve its own baseline.
2. Prepare the image outside admission using separately reviewed build inputs:
   digest-pinned base image, complete transitive dependency lock with artifact
   hashes, Python/system package versions, SBOM and build provenance. The image
   contains no repository code, secret, dataset, productive database or credentials.
   An administrator-controlled digest must identify the independently reviewed
   build. Do not publish or configure an unreviewed image to unblock CI.
3. In that disposable image run the 20 synthetic Git admission tests, the 43
   allowlisted guard tests, and the unchanged checker/diagnostic on reviewed
   engineering bytes. Require no skips; verify the diagnostic still reports
   `BLOCKED`, `HOLDOUT_EXPOSURE_CONFIRMED`, preserved incident evidence and exact
   historical counters `UNKNOWN`. Preserve logs, source hashes and image digest.
   Do not run historical suites, research, market acquisition or trading.
4. Independently review the new source allowlist and recompute the trusted
   manifest's blob identities/SHA-256 bindings, including this new document,
   SPEC and workflow. Preserve the original manifest and source version in Git
   history and preserve incident/snapshot/review bytes exactly. A candidate's
   rewritten manifest never authorizes itself: the independent reviewer must
   approve the complete final commit/tree and image outside the candidate.
5. Only after review and required receipts, an administrator records the exact
   full approved commit SHA in `OPERATIONAL_BASELINE_COMMIT` and the reviewed
   immutable image in `OPERATIONAL_ENGINEERING_IMAGE`, using the agreed protected
   configuration and branch review process. The connector used here cannot set
   those administration variables. Do not promote this draft tree as-is: its
   manifest has deliberately not been refreshed or approved.
6. Reproduce successful admission of the approved identical tree and rejection of
   altered tree, manifest, incident evidence, extra file, mutable/absent image and
   incorrect dependency versions. Verify required branch checks separately.

Until these steps are complete, keep this PR in draft and the existing operational
locks in effect. Successful engineering admission never enables research, M0,
FASE61, deployment or LIVE, and never repairs holdout independence.

## Verification completed for this draft

- Original 20 standard-library synthetic Git admission tests: PASS.
- All original manifest bindings except the proposed workflow remain byte-identical;
  original checker, manifest, incident, snapshot and review evidence are unchanged.
- Image allowlist checked against valid digest and adversarial invalid inputs.
- Full isolated guard execution is pending the separately approved image. This
  workspace does not have the exact isolated pytest/jsonschema environment.
- The manifest and administrator variables are unchanged. Rejection of this new
  tree by the original trusted checker is expected and must not be bypassed.
