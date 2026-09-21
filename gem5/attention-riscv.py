"""Hardware-owned SimObject mapping used by the isolated candidate runner."""

import argparse

import m5

from m5.objects import (
    AddrRange,
    Cache,
    DDR3_1600_8x8,
    L2XBar,
    MemCtrl,
    Process,
    RiscvO3CPU,
    RiscvTimingSimpleCPU,
    Root,
    SEWorkload,
    SrcClockDomain,
    System,
    SystemXBar,
    VoltageDomain,
)


BINARY = "/gem5-src/attention_kv_q4"


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def positive_float(value):
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def parse_args():
    parser = argparse.ArgumentParser(
        description="gem5 configuration for the Q4 attention proxy"
    )

    parser.add_argument(
        "--cpu-model",
        choices=("RiscvO3CPU", "RiscvTimingSimpleCPU"),
        required=True,
    )
    parser.add_argument("--cores", type=positive_int, required=True)
    parser.add_argument("--frequency-ghz", type=positive_float, required=True)
    parser.add_argument("--issue-width", type=positive_int, required=True)

    parser.add_argument("--l1i-cache-kib", type=positive_int, required=True)
    parser.add_argument("--l1i-associativity", type=positive_int, required=True)
    parser.add_argument("--l1i-latency-cycles", type=positive_int, required=True)

    parser.add_argument("--l1d-cache-kib", type=positive_int, required=True)
    parser.add_argument("--l1d-associativity", type=positive_int, required=True)
    parser.add_argument("--l1d-latency-cycles", type=positive_int, required=True)

    parser.add_argument("--l2-cache-kib", type=positive_int, required=True)
    parser.add_argument("--l2-associativity", type=positive_int, required=True)
    parser.add_argument("--l2-latency-cycles", type=positive_int, required=True)

    parser.add_argument(
        "--memory-type",
        choices=("DDR3_1600_8x8",),
        required=True,
    )
    parser.add_argument("--memory-size-mib", type=positive_int, required=True)
    parser.add_argument(
        "--simulation-mode",
        choices=("SE",),
        required=True,
    )

    parser.add_argument("--binary", default=BINARY)
    args = parser.parse_args()

    if args.cpu_model == "RiscvTimingSimpleCPU" and args.issue_width != 1:
        parser.error("RiscvTimingSimpleCPU requires --issue-width 1")

    return args


class L1InstructionCache(Cache):
    def __init__(self, size_kib, assoc, latency_cycles):
        super().__init__()

        self.size = f"{size_kib}KiB"
        self.assoc = assoc

        self.tag_latency = latency_cycles
        self.data_latency = latency_cycles
        self.response_latency = latency_cycles

        self.mshrs = 4
        self.tgts_per_mshr = 20


class L1DataCache(Cache):
    def __init__(self, size_kib, assoc, latency_cycles):
        super().__init__()

        self.size = f"{size_kib}KiB"
        self.assoc = assoc

        self.tag_latency = latency_cycles
        self.data_latency = latency_cycles
        self.response_latency = latency_cycles

        self.mshrs = 8
        self.tgts_per_mshr = 20


class L2Cache(Cache):
    def __init__(self, size_kib, assoc, latency_cycles):
        super().__init__()

        self.size = f"{size_kib}KiB"
        self.assoc = assoc

        self.tag_latency = latency_cycles
        self.data_latency = latency_cycles
        self.response_latency = latency_cycles

        self.mshrs = 20
        self.tgts_per_mshr = 12


args = parse_args()

cpu_types = {
    "RiscvO3CPU": RiscvO3CPU,
    "RiscvTimingSimpleCPU": RiscvTimingSimpleCPU,
}

memory_types = {
    "DDR3_1600_8x8": DDR3_1600_8x8,
}

system = System()

system.clk_domain = SrcClockDomain()
system.clk_domain.clock = "1GHz"
system.cpu_clk_domain = SrcClockDomain(
    clock=f"{args.frequency_ghz:g}GHz", voltage_domain=VoltageDomain()
)
system.clk_domain.voltage_domain = VoltageDomain()

system.mem_mode = "timing"
system.mem_ranges = [AddrRange(f"{args.memory_size_mib}MiB")]
system.multi_thread = True

cpu_type = cpu_types[args.cpu_model]
system.cpu = [cpu_type(cpu_id=core_id) for core_id in range(args.cores)]

system.membus = SystemXBar()
system.l2bus = L2XBar()

system.l2cache = L2Cache(
    args.l2_cache_kib,
    args.l2_associativity,
    args.l2_latency_cycles,
)

for cpu in system.cpu:
    cpu.clk_domain = system.cpu_clk_domain
    if args.cpu_model == "RiscvO3CPU":
        cpu.issueWidth = args.issue_width

    cpu.createInterruptController()

    cpu.icache = L1InstructionCache(
        args.l1i_cache_kib,
        args.l1i_associativity,
        args.l1i_latency_cycles,
    )
    cpu.dcache = L1DataCache(
        args.l1d_cache_kib,
        args.l1d_associativity,
        args.l1d_latency_cycles,
    )

    cpu.icache_port = cpu.icache.cpu_side
    cpu.dcache_port = cpu.dcache.cpu_side

    cpu.icache.mem_side = system.l2bus.cpu_side_ports
    cpu.dcache.mem_side = system.l2bus.cpu_side_ports

system.l2cache.cpu_side = system.l2bus.mem_side_ports
system.l2cache.mem_side = system.membus.cpu_side_ports

system.system_port = system.membus.cpu_side_ports

system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = memory_types[args.memory_type]()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

system.workload = SEWorkload.init_compatible(args.binary)

process = Process(pid=100)
process.cmd = [args.binary]

for cpu in system.cpu:
    cpu.workload = process
    cpu.createThreads()

root = Root(full_system=False, system=system)

m5.instantiate()

print("Starting Q4 attention simulation")
print(f"CPU: {args.cores} x {args.cpu_model}")
print(f"Issue width: {args.issue_width}")
print(f"Clock: {args.frequency_ghz:g}GHz")
print(f"L1 I-cache: {args.l1i_cache_kib}KiB, {args.l1i_associativity}-way per core")
print(f"L1 D-cache: {args.l1d_cache_kib}KiB, {args.l1d_associativity}-way per core")
print(f"L2 cache: {args.l2_cache_kib}KiB, {args.l2_associativity}-way shared")
print(f"Memory: {args.memory_type}, {args.memory_size_mib}MiB")
print("KV-cache format: packed Q4")
print("Software threads: 2")

exit_event = m5.simulate()

print(f"Exiting @ tick {m5.curTick()} because {exit_event.getCause()}")
