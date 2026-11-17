"""Initialize a pristine demonstration database without replacing existing history."""

from sqlalchemy import text
from .db import get_engine
from .pipeline import run_pipeline


def main():
    engine = get_engine()
    # Hold a session lock across the pipeline's separate transaction so two
    # startup containers cannot both decide that the database is pristine.
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(721303)"))
        try:
            empty = connection.scalar(
                text(
                    "SELECT NOT EXISTS (SELECT 1 FROM providers) "
                    "AND NOT EXISTS (SELECT 1 FROM encounters) "
                    "AND NOT EXISTS (SELECT 1 FROM scores) "
                    "AND NOT EXISTS (SELECT 1 FROM pipeline_runs)"
                )
            )
            if empty:
                run_pipeline(engine=engine)
                print("Initialized pristine synthetic demonstration data.")
            else:
                print("Existing synthetic data or run history preserved; bootstrap skipped.")
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(721303)"))


if __name__ == "__main__":
    main()
