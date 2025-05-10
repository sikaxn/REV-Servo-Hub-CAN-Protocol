import can
import tkinter as tk
from tkinter import ttk

# CAN Settings
CAN_CHANNEL = 0
CAN_BITRATE = 1000000

class RevServoHubCAN:
    def __init__(self, channel=CAN_CHANNEL, bustype='canalystii', bitrate=CAN_BITRATE):
        self.bus = can.interface.Bus(channel=channel, bustype=bustype, bitrate=bitrate)
        self.hub_id = 3  # Default hub ID

    def set_hub_id(self, hub_id: int):
        self.hub_id = hub_id

    def pause_to_bytes(self, pause: int) -> bytes:
        return pause.to_bytes(2, byteorder='little')

    def encode_run_power(self, run: list[int], power: list[int]) -> int:
        val = 0
        for i in range(3):
            val |= (run[i] << i) | (power[i] << (i + 3))
        return val

    def get_tx_id(self, group: int) -> int:
        base = 0x0C050000 if group == 0 else 0x0C050040
        return base | self.hub_id

    def send_command(self, group: int, pauses: list[int], run: list[int], power: list[int]):
        msg_id = self.get_tx_id(group)
        data = b''.join([self.pause_to_bytes(p) for p in pauses])
        data += self.encode_run_power(run, power).to_bytes(1, 'little')
        msg = can.Message(arbitration_id=msg_id, data=data, is_extended_id=True)
        self.bus.send(msg)

    def send_keepalive(self):
        fake_client_id = 0x000502C0
        msg = can.Message(arbitration_id=fake_client_id, data=bytes([0x01]), is_extended_id=True)
        self.bus.send(msg)


class ServoHubGUI:
    def __init__(self, root, hub: RevServoHubCAN):
        self.hub = hub
        self.root = root
        root.title("REV Servo Hub Control")

        self.pause = [tk.IntVar(value=1500) for _ in range(6)]
        self.power = [tk.IntVar(value=1) for _ in range(6)]
        self.run = [tk.IntVar(value=0) for _ in range(6)]
        self.hub_id_var = tk.IntVar(value=3)

        self.build_ui()
        self.keepalive_loop()

    def build_ui(self):
        # Hub ID selector
        id_frame = ttk.LabelFrame(self.root, text="Hub ID")
        id_frame.grid(row=0, column=0, columnspan=3, pady=5)
        id_dropdown = ttk.Combobox(
            id_frame, textvariable=self.hub_id_var, values=list(range(1, 64)), width=5, state="readonly"
        )
        id_dropdown.grid(row=0, column=0, padx=5, pady=5)
        id_dropdown.bind("<<ComboboxSelected>>", self.update_hub_id)

        # Channel sliders and toggles
        for i in range(6):
            ch_frame = ttk.LabelFrame(self.root, text=f"Channel {i}")
            ch_frame.grid(row=1 + i // 3, column=i % 3, padx=10, pady=5, sticky="nsew")

            ttk.Label(ch_frame, text="Pause:").grid(row=0, column=0)
            tk.Scale(
                ch_frame, from_=500, to=2500, variable=self.pause[i],
                orient="horizontal", command=lambda _, idx=i: self.update_channel(idx)
            ).grid(row=0, column=1)

            tk.Checkbutton(
                ch_frame, text="Power", variable=self.power[i],
                command=lambda idx=i: self.update_channel(idx)
            ).grid(row=1, column=0)
            tk.Checkbutton(
                ch_frame, text="Run", variable=self.run[i],
                command=lambda idx=i: self.update_channel(idx)
            ).grid(row=1, column=1)

    def update_hub_id(self, _=None):
        hub_id = self.hub_id_var.get()
        self.hub.set_hub_id(hub_id)
        self.send_all()

    def update_channel(self, idx):
        self.send_all()

    def send_all(self):
        for group in (0, 1):
            base = group * 3
            pauses = [self.pause[i].get() for i in range(base, base + 3)]
            run = [self.run[i].get() for i in range(base, base + 3)]
            power = [self.power[i].get() for i in range(base, base + 3)]
            self.hub.send_command(group, pauses, run, power)

    def keepalive_loop(self):
        self.hub.send_keepalive()
        self.root.after(100, self.keepalive_loop)


if __name__ == "__main__":
    hub = RevServoHubCAN()
    root = tk.Tk()
    app = ServoHubGUI(root, hub)
    root.mainloop()
