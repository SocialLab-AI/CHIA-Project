from pprint import pprint

from chia.base.ChiaFunction import get

from src.orchestration.nodes.hardware import run_gem5_baseline


def main():
    print("Submitting real gem5 experiment to CHIA...")

    result_ref = run_gem5_baseline.chia_remote()

    print("Experiment scheduled.")
    print("Waiting for gem5 simulation on hardware worker...")

    result = get(result_ref)

    print("\nCHIA hardware experiment completed.")
    print(f"Worker: {result['worker_hostname']}")
    print(f"Run ID: {result['run_id']}")
    print(f"Status: {result['status']['state']}")

    print("\nHardware configuration:")
    pprint(result["hardware"])

    print("\nMeasured gem5 metrics:")
    pprint(result["metrics"])


if __name__ == "__main__":
    main()
