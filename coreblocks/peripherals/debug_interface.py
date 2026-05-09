from amaranth.lib.data import StructLayout
from amaranth.lib.wiring import Component, Out
from transactron import Method, Methods, TModule, Transaction, def_method
from transactron.lib import FIFO
from transactron.utils import assign, logging
from transactron.utils.amaranth_ext.component_interface import COut, ComponentInterface

from coreblocks.interface import layouts
from coreblocks.params.genparams import GenParams

log = logging.HardwareLogger("debug.interface")


class DebugInterface(ComponentInterface):
    def __init__(self, gen_params: GenParams):
        self.pc = COut(gen_params.isa.xlen)
        self.reg_dst = COut(StructLayout({"rl_dst": gen_params.isa.reg_cnt_log, "val": gen_params.isa.xlen}))


class DebugInterfaceDriver(Component):
    iface: DebugInterface

    def __init__(self, gen_params: GenParams):
        self.debug_layouts = gen_params.get(layouts.DebugInterfaceLayouts)
        self.rf_layouts = gen_params.get(layouts.RFLayouts)

        read_port_cnt = gen_params.get(layouts.RFLayouts).rf_read_count

        self.emit = Method(i=self.debug_layouts.emit)
        self.read_req = Methods(read_port_cnt, i=self.rf_layouts.rf_read_in)
        self.read_resp = Methods(read_port_cnt, i=self.rf_layouts.rf_read_in, o=self.rf_layouts.rf_read_out)

        super().__init__({"iface": Out(DebugInterface(gen_params).signature)})

    def elaborate(self, platform):
        m = TModule()

        q_ret = FIFO(self.debug_layouts.emit, 2)

        @def_method(
            m,
            self.emit,
            # transactron skill sissue
            ready=q_ret.write.ready,
        )
        def _(pc, rl_dst, rp_dst):
            q_ret.write(m, pc=pc, rl_dst=rl_dst, rp_dst=rp_dst)
            self.read_req[-1](m, reg_id=rp_dst)

        with Transaction().body(m):
            ret = q_ret.read(m)

            pc = ret.pc
            rp_dst = ret.rp_dst
            rl_dst = ret.rl_dst

            resp = self.read_resp[-1](m, reg_id=rp_dst)
            reg_val = resp.reg_val
            valid = resp.valid

            log.assertion(m, valid, "read of invalid register {:x}", rl_dst)

            m.d.sync += self.iface.pc.eq(pc)
            m.d.sync += assign(self.iface.reg_dst, {"rl_dst": rl_dst, "val": reg_val})

        m.submodules.q_ret = q_ret
        log.assertion(m, self.emit.ready, "debug output not ready")

        return m
