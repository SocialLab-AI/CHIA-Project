"""Hardware-owned CLI mapper; preserves canonical units and explicit SimObject ownership."""


def build_gem5_command(config):
    args = []
    for field, value in config["hardware"].items():
        if field == "isa":
            continue
        args.extend(["--" + field.replace("_", "-"), str(value)])
    return args
