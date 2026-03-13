# Database Discipline & Safety Rules

This document outlines the strict rules that the AI Assistant MUST follow when interacting with the SQL Database (SQLite) or any stateful data stores in this project.

## I. The Golden Rule of Non-Destruction

The AI Assistant **must NEVER perform destructive operations on production tables** unless explicitly and unambiguously requested by the user.

Destructive operations include, but are not limited to:

- `DELETE FROM ...`
- `DROP TABLE ...`
- `TRUNCATE TABLE ...`
- `UPDATE ...` (without a highly specific, single-row `WHERE id = ?` clause)
- `db.query(Model).delete()` via SQLAlchemy.

## II. Testing and Mocking Principles

When writing scripts to test logic (e.g., race conditions, mutex locking, queue picking):

1. **Never use the main database file.** Do not interact with `data/auto_publisher.db` or `data/automation.db` for destructive testing.
2. **Use In-Memory SQLite or Temporary Files.** All simulated tests must spin up a `sqlite:///:memory:` instance or create an isolated `.sqlite` file in `/tmp/`.
3. **Never `DELETE` to "clean up".** If testing on a real table is absolutely necessary to observe an integration issue, you must ONLY `INSERT` new mock rows, and only modify those specific mock rows using their returned primary keys.

## III. Rollback Safety

Any standalone script written to debug database state must:

- Wrap operations in a transaction block.
- If the script modifies data to test an outcome, it MUST call `db.rollback()` at the end instead of `db.commit()`, ensuring the database state is left completely untouched after the test concludes.

## IV. Data Auditing

Before performing any operation that could affect more than 5 rows of data (even if safe), the Assistant must run a `SELECT COUNT(*)` to understand the blast radius and log it.

**Violating these rules indicates a severe breach of the "Personal-Stable" and production-ready philosophy of this project.**
