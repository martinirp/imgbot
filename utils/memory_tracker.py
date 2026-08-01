import struct

class MemoryTracker:
    def __init__(self, config):
        self.pid = config.get("mem_pid")
        self.ax  = config.get("mem_x_addr")
        self.ay  = config.get("mem_y_addr")
        self.az  = config.get("mem_z_addr")
        self.fmt = config.get("mem_fmt", "<H")
        self.size = struct.calcsize(self.fmt)

    def _read_val(self, addr):
        try:
            with open(f"/proc/{self.pid}/mem", "rb") as f:
                f.seek(addr)
                data = f.read(self.size)
                if len(data) == self.size:
                    return struct.unpack(self.fmt, data)[0]
        except Exception:
            pass
        return None

    def locate(self, frame=None, floor=None):
        if not self.pid or not self.ax:
            return {"found": False, "confidence": 0.0}
            
        x = self._read_val(self.ax)
        y = self._read_val(self.ay)
        z = self._read_val(self.az) if self.az else 7
        
        if x is not None and y is not None:
            return {
                "found": True,
                "x": x,
                "y": y,
                "z": z,
                "confidence": 1.0
            }
        return {"found": False, "confidence": 0.0}
