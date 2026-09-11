from src.tutor.runner import run_tutor
from src.hardware.runner import run_hardware

def run_experiment(config: dict) -> dict:
    """Execute both sides of one co-design experiment."""
    software_result = run_tutor(config["software"])
    hardware_result = run_hardware(config["hardware"])
    return {
        "software_result": software_result,
        "hardware_result": hardware_result,
    }
