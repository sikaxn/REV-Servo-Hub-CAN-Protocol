import can
import tkinter as tk
from tkinter import ttk, StringVar, IntVar, BooleanVar
from can.notifier import Notifier, Listener

# CAN Settings
CAN_CHANNEL = 0
CAN_BITRATE = 1000000

# Define REV Servo Hub class (same as your provided)
class RevServoHubCAN:
    def __init__(self, bus, hub_id=3):
        self.bus = bus
        self.hub_id = hub_id
        self.fake_fpga_counter = 0x2882b8fd
        self.counter_increment = 32152
        self.keepalive_mode = "none"

    def set_hub_id(self, hub_id: int):
        self.hub_id = hub_id

    def set_keepalive_mode(self, label: str):
        self.keepalive_mode = {
            "None": "none",
            "Hardware Client": "hardware",
            "roboRIO": "roborio"
        }.get(label, "none")

    def send_command(self, group: int, pauses: list[int], run: list[int], power: list[int]):
        base_id = 0x0C050000 if group == 0 else 0x0C050040
        msg_id = base_id | self.hub_id
        data = b''.join([int(p).to_bytes(2, byteorder='little') for p in pauses])
        control = sum((run[i] << i) | (power[i] << (i + 3)) for i in range(3))
        data += control.to_bytes(1, 'little')
        self.bus.send(can.Message(arbitration_id=msg_id, data=data, is_extended_id=True))

    def send_keepalive(self):
        if self.keepalive_mode == "hardware":
            self.send_fake_client_keepalive()
        elif self.keepalive_mode == "roborio":
            self.send_roborio_heartbeat()

    def send_fake_client_keepalive(self):
        msg = can.Message(arbitration_id=0x000502C0, data=[0x01], is_extended_id=True)
        self.bus.send(msg)

    def send_roborio_heartbeat(self):
        counter_bytes = self.fake_fpga_counter.to_bytes(4, byteorder='big')
        mode_byte = (1 << 4)  # Enabled
        data = list(counter_bytes) + [mode_byte, 0x00, 0x00, 0xFF]
        msg = can.Message(arbitration_id=0x01011840, data=data, is_extended_id=True)
        self.bus.send(msg)
        self.fake_fpga_counter = (self.fake_fpga_counter + self.counter_increment) % (2 ** 32)

# Define PDH handler
class RevPDHCAN:
    def __init__(self, bus, device_id=1):
        self.bus = bus
        self.device_id = device_id

    def set_device_id(self, did: int):
        self.device_id = did

    def send_switch_channel(self, enabled: bool):
        msg_id = 0x8050840 | self.device_id
        msg = can.Message(arbitration_id=msg_id, data=[0x01 if enabled else 0x00], is_extended_id=True)
        self.bus.send(msg)

# Notifier Listener
class PDHListener(Listener):
    def __init__(self, app):
        self.app = app

    def on_message_received(self, msg):
        self.app.handle_pdh_message(msg)

# Main App GUI
class CombinedGUI:
    def __init__(self, root):
        self.bus = can.interface.Bus(channel=CAN_CHANNEL, bustype='canalystii', bitrate=CAN_BITRATE)
        self.servo = RevServoHubCAN(self.bus)
        self.pdh = RevPDHCAN(self.bus)
        self.root = root

        self.channel_vars = [StringVar(value="0.00 A") for _ in range(24)]
        self.voltage_var = StringVar(value="Voltage: -- V")
        self.switch_var = BooleanVar(value=False)
        self.heartbeat_mode = StringVar(value="None")
        self.servo_id = IntVar(value=3)
        self.pdh_id = IntVar(value=1)

        self.pause = [IntVar(value=1500) for _ in range(6)]
        self.power = [IntVar(value=1) for _ in range(6)]
        self.run = [IntVar(value=0) for _ in range(6)]

        self.notifier = Notifier(self.bus, [PDHListener(self)])
        self.build_ui(root)
        self.keepalive_loop()

    def build_ui(self, root):
        root.title("REV PDH + Servo Hub UI")
        top = ttk.Frame(root)
        top.pack(pady=5)

        # IDs and heartbeat
        ttk.Label(top, text="Servo Hub ID:").pack(side="left")
        ttk.Combobox(top, values=list(range(0, 64)), textvariable=self.servo_id, width=4, state="readonly").pack(side="left")
        self.servo_id.trace_add("write", lambda *_: self.servo.set_hub_id(self.servo_id.get()))

        ttk.Label(top, text="Heartbeat:").pack(side="left")
        ttk.Combobox(top, values=["None", "Hardware Client", "roboRIO"], textvariable=self.heartbeat_mode, width=15, state="readonly").pack(side="left")
        self.heartbeat_mode.trace_add("write", lambda *_: self.servo.set_keepalive_mode(self.heartbeat_mode.get()))

        ttk.Label(top, text="PDH ID:").pack(side="left")
        ttk.Combobox(top, values=list(range(0, 64)), textvariable=self.pdh_id, width=4, state="readonly").pack(side="left")
        self.pdh_id.trace_add("write", lambda *_: self.pdh.set_device_id(self.pdh_id.get()))
        ttk.Checkbutton(top, text="Switch Channel", variable=self.switch_var, command=lambda: self.pdh.send_switch_channel(self.switch_var.get())).pack(side="left")

        ttk.Label(root, textvariable=self.voltage_var, font=("Segoe UI", 12)).pack(pady=5)

        # PDH current
        current_frame = ttk.LabelFrame(root, text="PDH Channel Currents")
        current_frame.pack(padx=10, pady=5)
        for i in range(24):
            ttk.Label(current_frame, text=f"CH{i:02}").grid(row=i // 4, column=(i % 4) * 2)
            ttk.Label(current_frame, textvariable=self.channel_vars[i], width=8).grid(row=i // 4, column=(i % 4) * 2 + 1)

        # Servo Hub Channels
        for i in range(6):
            ch_frame = ttk.LabelFrame(root, text=f"Servo Channel {i}")
            ch_frame.pack(padx=10, pady=2, fill="x")

            ttk.Label(ch_frame, text="Pause:").grid(row=0, column=0)
            tk.Scale(ch_frame, from_=500, to=2500, variable=self.pause[i], orient="horizontal", command=lambda _, idx=i: self.update_servo_channel(idx)).grid(row=0, column=1)
            tk.Checkbutton(ch_frame, text="Power", variable=self.power[i], command=lambda idx=i: self.update_servo_channel(idx)).grid(row=1, column=0)
            tk.Checkbutton(ch_frame, text="Run", variable=self.run[i], command=lambda idx=i: self.update_servo_channel(idx)).grid(row=1, column=1)

    def update_servo_channel(self, idx):
        for group in (0, 1):
            base = group * 3
            pauses = [self.pause[i].get() for i in range(base, base + 3)]
            run = [self.run[i].get() for i in range(base, base + 3)]
            power = [self.power[i].get() for i in range(base, base + 3)]
            self.servo.send_command(group, pauses, run, power)

    def handle_pdh_message(self, msg: can.Message):
        did = self.pdh_id.get()
        base_map = {
            0x8051800 | did: 0,
            0x8051840 | did: 6,
            0x8051880 | did: 12,
            0x80518C0 | did: 18
        }

        if msg.arbitration_id in base_map:
            base = base_map[msg.arbitration_id]
            if base == 18:
                for i in range(6):
                    self.channel_vars[base + i].set(f"{msg.data[i] * 0.0625:.2f} A")
            else:
                val = int.from_bytes(msg.data, 'little')
                for i in range(6):
                    raw = (val >> (i * 10)) & 0x3FF
                    self.channel_vars[base + i].set(f"{raw * 0.125:.2f} A")
        elif msg.arbitration_id == (0x8051900 | did):
            voltage = (int.from_bytes(msg.data[0:2], 'little') & 0xFFF) * 0.0078125
            self.voltage_var.set(f"Voltage: {voltage:.2f} V")

    def keepalive_loop(self):
        self.servo.send_keepalive()
        self.root.after(100, self.keepalive_loop)

root = tk.Tk()
app = CombinedGUI(root)
root.mainloop()
