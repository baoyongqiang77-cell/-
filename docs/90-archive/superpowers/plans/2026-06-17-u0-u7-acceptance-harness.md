# U0-U7 Acceptance Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, testable acceptance harness for U0-U7 that validates the documented project rules without pretending unresolved production integrations are complete.

**Architecture:** Implement a Python standard-library domain package under `src/drone_inspection` with one service module per development unit. Unit tests under `tests` drive each rule first, and Markdown reports under `docs/tests` record acceptance evidence and blocked production items.

**Tech Stack:** Python standard library, `unittest`, Markdown test reports.

---

### Task 1: U0-U7 Red Tests

**Files:**
- Create: `tests/test_u0_foundation.py`
- Create: `tests/test_u1_flight.py`
- Create: `tests/test_u2_media_analysis.py`
- Create: `tests/test_u3_inference_runtime.py`
- Create: `tests/test_u4_annotation.py`
- Create: `tests/test_u5_training_release.py`
- Create: `tests/test_u6_algorithms.py`
- Create: `tests/test_u7_acceptance.py`

- [ ] Write tests that import the desired package API and assert the required project rules.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Expected result: import failures because production modules do not exist yet.

### Task 2: Minimal Domain Implementation

**Files:**
- Create: `src/drone_inspection/__init__.py`
- Create: `src/drone_inspection/errors.py`
- Create: `src/drone_inspection/constants.py`
- Create: `src/drone_inspection/foundation.py`
- Create: `src/drone_inspection/flight.py`
- Create: `src/drone_inspection/media_analysis.py`
- Create: `src/drone_inspection/inference.py`
- Create: `src/drone_inspection/annotation.py`
- Create: `src/drone_inspection/training.py`
- Create: `src/drone_inspection/algorithms.py`
- Create: `src/drone_inspection/acceptance.py`

- [ ] Implement only the behavior required by the tests.
- [ ] Keep all unresolved production dependencies represented as explicit pending gates.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Expected result: all tests pass.

### Task 3: Test Reports

**Files:**
- Create: `docs/tests/U0-foundation-test-report.md`
- Create: `docs/tests/U1-flight-test-report.md`
- Create: `docs/tests/U2-media-analysis-test-report.md`
- Create: `docs/tests/U3-inference-runtime-test-report.md`
- Create: `docs/tests/U4-annotation-test-report.md`
- Create: `docs/tests/U5-training-release-test-report.md`
- Create: `docs/tests/U6-algorithm-acceptance-test-report.md`
- Create: `docs/tests/U7-system-acceptance-test-report.md`
- Create: `docs/tests/FINAL_TEST_REPORT.md`

- [ ] Record automated test command, acceptance scope, pass/fail status, and blocked real-world prerequisites.
- [ ] Mark U6/M2 real algorithm acceptance and U7 production acceptance as blocked until the documented external evidence exists.
- [ ] Run a final full test command and update `FINAL_TEST_REPORT.md` with the fresh result.
