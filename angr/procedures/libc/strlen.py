import claripy
import angr
from angr.sim_options import MEMORY_CHUNK_INDIVIDUAL_READS
from angr.storage.memory_mixins.regioned_memory.abstract_address_descriptor import AbstractAddressDescriptor

import logging
l = logging.getLogger(name=__name__)

class strlen(angr.SimProcedure):
    #pylint:disable=arguments-differ
    max_null_index = None

    def run(self, s, wchar=False):
        if wchar:
            null_seq = self.state.solver.BVV(0, 16)
            step = 2
        else:
            null_seq = self.state.solver.BVV(0, 8)
            step = 1

        max_symbolic_bytes = self.state.libc.buf_symbolic_bytes
        max_str_len = self.state.libc.max_str_len

        chunk_size = None
        if MEMORY_CHUNK_INDIVIDUAL_READS in self.state.options:
            chunk_size = 1

        if self.state.mode == 'static':

            self.max_null_index = 0

            # Make sure to convert s to ValueSet
            addr_desc: AbstractAddressDescriptor = self.state.memory._normalize_address(s)

            length = self.state.solver.ESI(self.state.arch.bits)
            for s_aw in self.state.memory._concretize_address_descriptor(addr_desc, None):

                s_ptr = s_aw.to_valueset(self.state)
                r, c, i = self.state.memory.find(s, null_seq, max_str_len, max_symbolic_bytes=max_symbolic_bytes, step=step, chunk_size=chunk_size)

                self.max_null_index = max([self.max_null_index] + i)

                # Convert r to the same region as s
                r_desc = self.state.memory._normalize_address(r)
                r_aw_iter = self.state.memory._concretize_address_descriptor(r_desc, None, target_region=next(iter(s_ptr._model_vsa.regions.keys())))

                for r_aw in r_aw_iter:
                    r_ptr = r_aw.to_valueset(self.state)
                    length = length.union(r_ptr - s_ptr)

            return length

        else:
            search_len = max_str_len
            r, c, i = self.state.memory.find(s, null_seq, search_len, max_symbolic_bytes=max_symbolic_bytes, step=step, chunk_size=chunk_size)

            # try doubling the search len and searching again
            s_new = s
            while c and all(con.is_false() for con in c):
                s_new += search_len
                search_len *= 2
                r, c, i = self.state.memory.find(s_new, null_seq, search_len, max_symbolic_bytes=max_symbolic_bytes, step=step, chunk_size=chunk_size)
                # stop searching after some reasonable limit
                if search_len > 0x10000:
                    raise angr.SimMemoryLimitError("strlen hit limit of 0x10000")

            self.max_null_index = max(i)
            self.state.add_constraints(*c)
            result = r - s
            if result.depth > 3:
                rresult = claripy.BVS('strlen', len(result))
                self.state.solver.add(result == rresult)
                result = rresult
            return result
