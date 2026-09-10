import m5

from m5.objects import (
    AddrRange,
    Cache,
    DDR3_1600_8x8,
    L2XBar,
    MemCtrl,
    Process,
    RiscvO3CPU,
    Root,
    SEWorkload,
    SrcClockDomain,
    System,
    SystemXBar,
    VoltageDomain,
)


BINARY = "/gem5-src/attention_kv_q4"
NUM_CORES = 2


class L1InstructionCache(Cache):
    size = "16KiB"
    assoc = 2

    tag_latency = 2
    data_latency = 2
    response_latency = 2

    mshrs = 4
    tgts_per_mshr = 20


class L1DataCache(Cache):
    size = "64KiB"
    assoc = 4

    tag_latency = 2
    data_latency = 2
    response_latency = 2

    mshrs = 8
    tgts_per_mshr = 20


class L2Cache(Cache):
    size = "1MiB"
    assoc = 8

    tag_latency = 20
    data_latency = 20
    response_latency = 20

    mshrs = 20
    tgts_per_mshr = 12


system = System()

system.clk_domain = SrcClockDomain()
system.clk_domain.clock = "1GHz"
system.clk_domain.voltage_domain = VoltageDomain()

system.mem_mode = "timing"
system.mem_ranges = [AddrRange("16MiB")]
system.multi_thread = True

system.cpu = [
    RiscvO3CPU(cpu_id=core_id)
    for core_id in range(NUM_CORES)
]

system.membus = SystemXBar()
system.l2bus = L2XBar()
system.l2cache = L2Cache()

for cpu in system.cpu:
    cpu.issueWidth = 2
    cpu.createInterruptController()

    cpu.icache = L1InstructionCache()
    cpu.dcache = L1DataCache()

    cpu.icache_port = cpu.icache.cpu_side
    cpu.dcache_port = cpu.dcache.cpu_side

    cpu.icache.mem_side = system.l2bus.cpu_side_ports
    cpu.dcache.mem_side = system.l2bus.cpu_side_ports

system.l2cache.cpu_side = system.l2bus.mem_side_ports
system.l2cache.mem_side = system.membus.cpu_side_ports

system.system_port = system.membus.cpu_side_ports

system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

system.workload = SEWorkload.init_compatible(BINARY)

process = Process(pid=100)
process.cmd = [BINARY]

for cpu in system.cpu:
    cpu.workload = process
    cpu.createThreads()

root = Root(full_system=False, system=system)

m5.instantiate()

print("Starting Q4 attention simulation")
print("CPU: 2 x RiscvO3CPU")
print("Issue width: 2")
print("Clock: 1GHz")
print("L1 I-cache: 16KiB, 2-way per core")
print("L1 D-cache: 64KiB, 4-way per core")
print("L2 cache: 1MiB, 8-way shared")
print("Memory: DDR3_1600_8x8, 16MiB")
print("KV-cache format: packed Q4")
print("Software threads: 2")

exit_event = m5.simulate()

print(
    f"Exiting @ tick {m5.curTick()} "
    f"because {exit_event.getCause()}"
)
