def build_run_record(
    *,
    schema_version: str,
    run_id: str,
    experiment_id: str,
    status: str,
    **kwargs,
) -> dict:
    """Build a run record using the version defined by the canonical contract."""
    record = {
        "schema_version": schema_version,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "status": status,
    }
    record.update(kwargs)
    return record
