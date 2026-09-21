"""CHIA graph scheduling boundary."""

from src.common.candidate import ROOT
from src.common.errors import (
    ExecutionTimeout,
    PreflightError,
)
from src.orchestration.nodes.evaluation import evaluation_node
from src.orchestration.nodes.energy import energy_node
from src.orchestration.nodes.hardware import hardware_node
from src.orchestration.nodes.shared import execute_runtime
from src.orchestration.nodes.software import software_node
from src.orchestration.nodes.validation import (
    mapping_node,
    validation_node,
)


FUNCTIONS = {
    "validation": validation_node,
    "mapping": mapping_node,
    "software": software_node,
    "hardware": hardware_node,
    "energy": energy_node,
    "evaluation": evaluation_node,
}

RESOURCES = {
    "validation": {"control": 0.01},
    "mapping": {"control": 0.01},
    "evaluation": {"control": 0.01},
    "software": {"llama_cpp": 1},
    "hardware": {"gem5": 1},
    "energy": {"gem5": 1},
}


class LocalDispatcher:
    """Run the same nodes locally without Ray scheduling."""

    def submit(self, name, *args):
        return FUNCTIONS[name](*args)

    def get(self, reference, timeout=None):
        return reference

    def cancel(self, reference):
        return None


class ChiaDispatcher:
    """Schedule graph nodes through CHIA and Ray."""

    def __init__(self, address="auto", *, env_vars=None):
        try:
            import ray
            from chia.base.ChiaFunction import ChiaFunction
        except ImportError as error:
            raise PreflightError(
                "Install the cluster extra before selecting "
                "CHIA execution."
            ) from error

        self.ray = ray

        if not ray.is_initialized():
            init_options = {}
            runtime_env = {}

            if (
                isinstance(address, str)
                and address.startswith("ray://")
            ):
                runtime_env["working_dir"] = str(ROOT)

            if env_vars:
                runtime_env["env_vars"] = dict(env_vars)

            if runtime_env:
                init_options["runtime_env"] = runtime_env

            ray.init(
                address=address,
                **init_options,
            )

        available = ray.cluster_resources()

        for resource in (
            "control",
            "llama_cpp",
            "gem5",
        ):
            if available.get(resource, 0) < 1:
                raise PreflightError(
                    f"Cluster lacks required "
                    f"{resource} resource."
                )

        node_runtime_env = (
            {"env_vars": dict(env_vars)}
            if env_vars
            else None
        )

        self.nodes = {
            name: ChiaFunction(
                resources=RESOURCES[name],
                num_cpus=(
                    4
                    if name == "software"
                    else 1
                ),
                max_retries=0,
                retry_exceptions=False,
                runtime_env=node_runtime_env,
            )(function)
            for name, function in FUNCTIONS.items()
        }

    def submit(self, name, *args):
        return self.nodes[name].chia_remote(*args)

    def get(self, reference, timeout=None):
        try:
            return self.ray.get(
                reference,
                timeout=timeout,
            )
        except self.ray.exceptions.GetTimeoutError as error:
            raise ExecutionTimeout(
                "CHIA task did not finish before "
                "the campaign deadline."
            ) from error

    def cancel(self, reference):
        try:
            from chia.base.ChiaFunction import chia_cancel

            chia_cancel(
                reference,
                force=True,
            )
        except ImportError:
            self.ray.cancel(
                reference,
                force=True,
            )
