from src.hardware.runner import run_hardware
from src.tutor.runner import run_tutor


def run_experiment(config: dict) -> dict:
    """Execute both sides of one canonical co-design experiment."""
    software_result = run_tutor(config)
    hardware_result = run_hardware(config)

    return {
        "software_result": software_result,
        "hardware_result": hardware_result,
    }
