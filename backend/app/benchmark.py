"""Run against the synthetic demo database. This replaces its current dataset."""

import json
import platform
import statistics
import time
from sqlalchemy import text
from sqlalchemy.orm import Session
from .db import get_engine
from .pipeline import run_pipeline
from .repository import search


def main():
    engine = get_engine()
    start = time.perf_counter()
    run_pipeline(engine=engine)
    ingest = time.perf_counter() - start
    samples = []
    with Session(engine) as session:
        for _ in range(5):
            search(session, "", "Cardiology", None, None, None, 1, 20, "quality")
        for _ in range(100):
            start = time.perf_counter()
            result = search(session, "", "Cardiology", None, None, None, 1, 20, "quality")
            assert result["total"] == 200
            samples.append((time.perf_counter() - start) * 1000)
        version = session.scalar(text("SELECT version()"))
    print(
        json.dumps(
            {
                "providers": 1000,
                "encounters": 100000,
                "seed": 42,
                "pipeline_seconds": round(ingest, 3),
                "search_runs": 100,
                "warmups": 5,
                "search_median_ms": round(statistics.median(samples), 3),
                "search_p95_ms": round(sorted(samples)[94], 3),
                "python": platform.python_version(),
                "postgresql": version,
                "method": "In-process SQLAlchemy count + filtered page + serialization; not HTTP latency or a load test",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
