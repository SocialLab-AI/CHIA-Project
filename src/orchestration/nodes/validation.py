"""Control-plane nodes for immutable validation and runtime knob routing; integration owned."""

from src.common.candidate import Candidate
from src.common.logging import invoke
from src.hardware.gem5 import build_gem5_command
from src.hardware.attention_kernel import build_attention_kernel_args
from src.tutor.runner import inference_mapping


def validation_node(config, context):
    return invoke("validation", context, lambda: Candidate.from_dict(config).config)


def mapping_node(validated, context):
    if validated["event"]["status"] != "completed":
        return validated

    def mapping():
        config = validated["value"]
        return {
            "candidate": config,
            "hardware_argv": build_gem5_command(config),
            "kernel_defines": build_attention_kernel_args(config),
            "inference": inference_mapping(config["software"]),
        }

    return invoke("mapping", context, mapping)
