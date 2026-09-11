def build_run_record(*, run_id: str, experiment_id: str, status: str, **kwargs) -> dict:
    record = {
        "schema_version": "1.0",
        "run_id": run_id,
        "experiment_id": experiment_id,
        "status": status,
    }
    record.update(kwargs)
    return record
