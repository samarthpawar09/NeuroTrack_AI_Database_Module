# NeuroTrack AI — SQLite database module

## Files
- `database.py`: database functions and secure password hashing (Python standard library).
- `schema.sql`: table definitions and indexes.
- `test_database.py`: tests using a temporary database.
- `check_database.py`: Verifies database tables and their columns.
- `database/neurotrack.db`: created locally by `init_db()`; do not commit it.

## Requirements
Python 3.10+; no third-party package is required for this module.

## Initialize
From the `NeuroTrack_AI` project directory:

```bash
python -c "from database import init_db; init_db(); print('Database initialized')"
```

This creates `database/neurotrack.db`.

## Run tests

```bash
python -m unittest -v test_database.py
```

## Function signatures

```python
init_db(db_path=None) -> None
create_user(full_name, email, password, db_path=None) -> int
get_user_by_email(email, db_path=None) -> dict | None
save_assessment(user_id, assessment, db_path=None) -> str
get_user_assessments(user_id, db_path=None) -> list[dict]
get_assessment_by_id(assessment_id, user_id, db_path=None) -> dict | None
verify_password(password, password_hash) -> bool
```

`db_path` is optional and mainly useful for tests. Production calls use the default
`database/neurotrack.db`.

## Example integration

```python
from database import (
    create_user, get_user_by_email, verify_password,
    save_assessment, get_user_assessments, get_assessment_by_id,
)

# Registration
user_id = create_user("Asha Patil", "asha@example.com", "a-long-password")

# Authentication
user = get_user_by_email("asha@example.com")
if user and verify_password("a-long-password", user["password_hash"]):
    print("Authenticated")

# After the existing assessment service has produced its complete result:
assessment_id = save_assessment(user_id, assessment_result)

# History and detail — always pass the authenticated user's ID.
history = get_user_assessments(user_id)
detail = get_assessment_by_id(assessment_id, user_id)
```
**Note:** Example names, emails and passwords are for demonstration
only. Never hardcode real user credentials in production.

## Integration notes
- `save_assessment()` takes the full assessment object and extracts `scores`,
  `domain_scores`, metadata, and nested domain/question responses.
- The UUID from the assessment service is retained (validated as a UUID).
- Timestamps are normalized to UTC ISO-8601 strings ending in `Z`.
- Assessment and response inserts run in one SQLite transaction.
- `get_assessment_by_id()` requires both `assessment_id` and `user_id`, preventing
  retrieval of another user's assessment by guessing a UUID.
- The incoming `status` is stored as provided. The sample value
  `processed_not_saved` is not silently rewritten; coordinate any status rename with
  the Flask/backend developer.
- The `predictions` table is created for future integration, but this module never
  creates predictions or inserts artificial dementia-risk values.
- Passwords are hashed using Python's built-in scrypt implementation. Do not return
  `password_hash` in API responses or logs.
- Add `database/neurotrack.db` to `.gitignore`.
- The backend developer must coordinate assessment status handling.
  The database module stores the incoming status without automatically changing its meaning.
