# Generic single-database configuration

## INIT

```bash
alembic init alembic # Create alembic directory
alembic revision --autogenerate --rev-id initial # Create initial migration
alembic upgrade head # Apply the initial migration
```

## Create a new migration version

```bash
alembic revision --autogenerate --rev-id <revision_id> # Create a new migration file
```

## Upgrade - Downgrade

```bash
alembic upgrade head    # Upgrade to latest revision
```

```bash
alembic upgrade <revision_id>   # Upgrade to a specific revision
```

```bash
alembic downgrade -1    # Downgrade one step
```

```bash
alembic downgrade <revision_id> # Downgrade to a specific revision
```

```bash
alembic downgrade base  # Downgrade everything (clean slate)
```

```bash
alembic history # Show all revisions (with IDs and messages)
```

```bash
alembic current # Show the current applied revision in the DB
```

```bash
alembic heads   # Show the latest revision(s)
```
