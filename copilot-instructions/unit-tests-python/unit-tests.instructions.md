---
description: Unit test creation and maintenance standards for pytest test work in this repository.
applyTo: "tests/**/*.py"
---

# Unit Test Instructions: pytest

## Purpose and Scope
These instructions define how GitHub Copilot should create and maintain unit tests in this repository.

Scope restriction:
- These instructions apply only to creating and maintaining unit tests and their direct test support files.
- These instructions do not apply to production feature development, refactoring, or infrastructure tasks.

Hard constraints:
- Do not modify production source files while building or updating unit tests.
- Use pytest for all unit tests.
- Keep tests deterministic and isolated from external services unless explicitly required.

## How This Instructions File Is Used
When a request involves creating, updating, or validating unit tests, Copilot must:
1. Follow this file as the primary standard for test structure, naming, implementation style, and validation.
2. Generate any missing unit test modules and test functions required by these rules.
3. Validate test execution and fix test-project issues until tests run successfully, without changing production source files.
4. Keep all test artifacts aligned with these requirements over time.

## Source-to-Test Mapping Rules
Tests should mirror the source structure under src where practical.

Rules:
- Source modules under src/pilot_api should map to corresponding areas under tests.
- Example mapping:
  - src/pilot_api/service/crud_service.py -> tests/service/test_crud_service.py
  - src/pilot_api/api/routes/resources.py -> tests/api/test_resources.py
- Shared fixtures and reusable setup should live in tests/conftest.py or focused helper modules under tests.

## Test Directory Structure Rules
The arrangement of tests should reflect the arrangement of source modules.

Requirements:
- Mirror source directories for service, repository, api, validation, and other layers where possible.
- Keep feature-specific test resources close to related tests when practical.
- Use support directories under tests when needed, for example:
  - tests/doubles
  - tests/resources
  - tests/utilities

## Coverage Requirements
Each production behavior should have matching tests.

Rules:
- If matching tests do not exist, create them.
- Cover primary logic paths and edge cases.
- Include positive and negative outcomes.
- Add regression tests for discovered defects.
- Validate tests after creating or updating test logic.

## Test Naming and Style Conventions
Use pytest-native test style.

Conventions:
- Prefer function-based tests unless class grouping adds clear value.
- Test module names should start with test_.
- Test function naming format:
  - test_<unit_under_test>_<behavior>_<expected_outcome>
- Follow Arrange, Act, Assert structure in test bodies.
- Avoid unnecessary shared mutable state across tests.

Variable and fixture rules:
- Use descriptive variable names.
- Keep fixture scope as small as practical.
- Prefer explicit fixture names and values for readability.

## Validation and Error Correction
After creating or updating tests, verify tests run successfully.

Requirements:
- Run relevant tests frequently during changes.
- Typical commands:
  - python -m pytest
  - python -m pytest tests/path/to/test_file.py -q
- Correct discovered test issues.
- Do not alter production source files solely to make tests pass during test-only tasks.

## Appendix A: Additional Best Practices and Recommendations

1. Test design quality
- Keep each test focused on one behavior.
- Prefer one assertion theme per test.
- Use explicit input values to make intent obvious.
- Include happy-path, boundary, null or empty, invalid input, and exception-path tests where applicable.

2. Deterministic tests
- Avoid reliance on current time, random values, external state, network calls, and environment-specific behavior unless fully controlled by fixtures or doubles.
- Use stable test data and controlled setup.

3. Readability and maintainability
- Keep Arrange, Act, Assert sections visually clear.
- Use descriptive test and fixture names.
- Avoid unnecessary mocking; prefer behavior-focused tests with minimal indirection.

4. Doubles and resources
- Place reusable doubles under tests/doubles.
- Place helper utilities under tests/utilities.
- Place test resources under tests/resources and reference them predictably.

5. Coverage discipline
- Add tests for both positive and negative outcomes.
- Add regression tests when defects are found.
- Ensure new or changed behaviors are not left without test coverage.

6. File and module hygiene
- Keep folder organization aligned with the source tree.
- Keep test modules cohesive and focused by behavior.

7. Execution workflow recommendation
- Create or update tests incrementally per source module.
- Run tests frequently during changes.
- Resolve failures immediately before moving to the next module.
