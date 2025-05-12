import can
import tkinter as tk
from tkinter import ttk

# CAN Settings
CAN_CHANNEL = 0
CAN_BITRATE = 1000000

class RevPneumaticHubCAN:
    def __init__(self, channel=CAN_CHANNEL, bustype='canalystii', bitrate=CAN_BITRATE):
        self.bus = can.interface.Bus(channel=channel, bustype=bustype, bitrate=bitrate)
        self.hub_id = 1
        self.fake_fpga_counter = 0x2882b8fd
        self.counter_increment = 32152
        self.keepalive_mode = "none"  # one of: "none", "hardware", "roborio"

        self.channels = [False] * 16
        self.compressor_on = False
        self.closed_loop = False

    def set_hub_id(self, hub_id: int):
        self.hub_id = hub_id

    def set_keepalive_mode(self, label: str):
        lookup = {
            "None": "none",
            "Hardware Client": "hardware",
            "roboRIO": "roborio"
        }
        self.keepalive_mode = lookup.get(label, "none")

    def send_solenoids(self):
        sol_mask = sum(1 << i for i, state in enumerate(self.channels) if state)
        data = sol_mask.to_bytes(2, byteorder='little') + bytes(6)
        msg_id = 0x02040000 | (self.hub_id << 16) | 0x0200
        msg = can.Message(arbitration_id=msg_id, data=data, is_extended_id=True)
        self.bus.send(msg)

    def send_compressor_control(self):
        flags = (0x01 if self.compressor_on else 0x00) | (0x02 if self.closed_loop else 0x00)
        data = bytes([flags]) + bytes(7)
        msg_id = 0x02040000 | (self.hub_id << 16) | 0x0400
        msg = can.Message(arbitration_id=msg_id, data=data, is_extended_id=True)
        self.bus.send(msg)

    def send_keepalive(self):
        if self.keepalive_mode == "hardware":
            self.send_fake_client_keepalive()
        elif self.keepalive_mode == "roborio":
            self.send_roborio_heartbeat()

    def send_fake_client_keepalive(self):
        msg = can.Message(arbitration_id=0x000502C0, data=bytes([0x01]), is_extended_id=True)
        self.bus.send(msg)

    def send_roborio_heartbeat(self, enabled=True, auto=False, test=False, alliance_red=False, countdown=None):
        UNIVERSAL_HEARTBEAT_CAN_ID = 0x01011840
        counter_bytes = self.fake_fpga_counter.to_bytes(4, byteorder='big')
        mode_byte = 0
        if enabled: mode_byte |= (1 << 4)
        if test: mode_byte |= (1 << 3)
        if auto: mode_byte |= (1 << 2)
        if alliance_red: mode_byte |= (1 << 0)
        byte7 = countdown if countdown is not None else 0xFF
        data = list(counter_bytes) + [mode_byte, 0x00, 0x00, byte7]
        msg = can.Message(arbitration_id=UNIVERSAL_HEARTBEAT_CAN_ID, data=data, is_extended_id=True)
        self.bus.send(msg)
        self.fake_fpga_counter = (self.fake_fpga_counter + self.counter_increment) % (2 ** 32)

class PneumaticHubGUI:
    def __init__(self, root, hub: RevPneumaticHubCAN):
        self.hub = hub
        self.root = root
        root.title("REV Pneumatic Hub Control")

        self.hub_id_var = tk.IntVar(value=1)
        self.heartbeat_mode_var = tk.StringVar(value="None")
        self.compressor_on = tk.BooleanVar()
        self.closed_loop = tk.BooleanVar()
        self.channel_vars = [tk.BooleanVar() for _ in range(16)]

        self.build_ui()
        self.keepalive_loop()

    def build_ui(self):
        control_frame = ttk.LabelFrame(self.root, text="Settings")
        control_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        ttk.Label(control_frame, text="Hub ID:").grid(row=0, column=0)
        hubid_box = ttk.Combobox(control_frame, textvariable=self.hub_id_var, values=list(range(1, 64)), width=5, state="readonly")
        hubid_box.grid(row=0, column=1)
        hubid_box.bind("<<ComboboxSelected>>", lambda e: self.hub.set_hub_id(self.hub_id_var.get()))

        ttk.Label(control_frame, text="Heartbeat:").grid(row=0, column=2)
        hb_box = ttk.Combobox(control_frame, textvariable=self.heartbeat_mode_var, values=["None", "Hardware Client", "roboRIO"], width=15, state="readonly")
        hb_box.grid(row=0, column=3)
        hb_box.bind("<<ComboboxSelected>>", lambda e: self.hub.set_keepalive_mode(self.heartbeat_mode_var.get()))

        comp_frame = ttk.LabelFrame(self.root, text="Compressor")
        comp_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        ttk.Checkbutton(comp_frame, text="Enable Compressor", variable=self.compressor_on,
                        command=self.send_compressor).grid(row=0, column=0)
        ttk.Checkbutton(comp_frame, text="Closed Loop", variable=self.closed_loop,
                        command=self.send_compressor).grid(row=0, column=1)

        sol_frame = ttk.LabelFrame(self.root, text="Solenoids")
        sol_frame.grid(row=2, column=0, columnspan=3, padx=5, pady=5)
        for i in range(16):
            r, c = divmod(i, 8)
            chk = ttk.Checkbutton(sol_frame, text=f"CH{i}", variable=self.channel_vars[i],
                                  command=self.send_solenoids)
            chk.grid(row=r, column=c, padx=2, pady=2)

    def send_solenoids(self):
        self.hub.channels = [v.get() for v in self.channel_vars]
        self.hub.send_solenoids()

    def send_compressor(self):
        self.hub.compressor_on = self.compressor_on.get()
        self.hub.closed_loop = self.closed_loop.get()
        self.hub.send_compressor_control()

    def keepalive_loop(self):
        self.hub.send_keepalive()
        self.root.after(100, self.keepalive_loop)

if __name__ == "__main__":
    hub = RevPneumaticHubCAN()
    root = tk.Tk()
    app = PneumaticHubGUI(root, hub)
    root.mainloop()
