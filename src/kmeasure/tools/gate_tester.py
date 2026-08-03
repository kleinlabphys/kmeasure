from numbers import Number
import sys 

import numpy as np

import pyqtgraph as pg
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, Signal

from kmeasure import ramp


class LivePlotter(QtWidgets.QMainWindow):

    spacebar_pressed = Signal()
    escape_pressed = Signal()

    def __init__(self):
        super().__init__()

        #anti aliasing
        pg.setConfigOptions(antialias=True)

        # window
        self.setWindowTitle("Live Plotter") # default window title, change later with this method

        # Create graph widget
        self.graphWidget = pg.PlotWidget()
        self.setCentralWidget(self.graphWidget)

        # plot style
        self.graphWidget.setBackground('w')
        self.graphWidget.setTitle(f"", color="b", size="16pt")
        self.graphWidget.showGrid(x=True, y=True, alpha=0.3)

        # data buffers
        self.x_data = [0]
        self.y_data = [0]

        # line reference
        modern_blue = (41, 128, 185)
        pen = pg.mkPen(color=modern_blue, width=2)
        self.data_line = self.graphWidget.plot(self.x_data, self.y_data, pen=pen)

        self.timer = QtCore.QTimer()
        self.timer.setInterval(50)  # Slowed down slightly - 15ms is often too fast for hardware gate.get() calls!
        self.timer.start()

    def update_plot_data(self, new_x_value, new_y_value):

        self.x_data.append(new_x_value)
        self.y_data.append(new_y_value)

        # update plot line
        self.data_line.setData(self.x_data, self.y_data)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            print("escape pressed")
            self.escape_pressed.emit()
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            print("spacebar pressed")
            self.spacebar_pressed.emit()
        else:
            print(f"Character pressed: {event.text()}")

        super().keyPressEvent(event)

class GateTester:
    def __init__(self, gate_voltage_qcodes_param, gate_current_qcodes_param, slew_rate=0.1, V_range:tuple[Number, Number]=(-10,10), param_increment=0.01, min_inter_delay=0.05):
        self.gate_voltage = gate_voltage_qcodes_param
        self.gate_current = gate_current_qcodes_param
        self.slew_rate = slew_rate
        self.V_range = V_range
        self.param_increment = param_increment
        self.min_inter_delay = min_inter_delay
        
        self.target_idx = 1 # Start by ramping towards V_range[1]
        self.timestamp = 0
        self.ramp_thread = None

    def run(self):
        # prevent crashing if a QApplication already exists
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.main = LivePlotter()

        # GUI stuff
        self.main.setWindowTitle("Gate Tester")
        self.main.graphWidget.setTitle(f"[SPACE] Change direction   |   [ESC] Close", size="14pt")
        self.main.graphWidget.setLabel('left', 'Current (A)', color='black', size=16)
        self.main.graphWidget.setLabel('bottom', 'Voltage (V)', color='black', size=16)
        
        # connect signals to controller methods
        self.main.spacebar_pressed.connect(self.reverse_ramp)
        self.main.timer.timeout.connect(self.poll_instrument)

        print("[GATE TEST] Ramping to 0V.")
        # ramp gate to 0V (blocking)
        ramp(
            self.gate_voltage, 
            0, 
            slew_rate=self.slew_rate, 
            param_increment=self.param_increment, 
            min_inter_delay=self.min_inter_delay, 
            verbose=True, 
            blocking=True)
        # start the initial ramp
        self.start_ramp()

        self.main.show()
        self.app.exec()

    def start_ramp(self):
        try:
            target_v = self.V_range[self.target_idx]
            print(f"[GATE TEST] Ramping to {target_v}.")

            if self.ramp_thread is not None:
                self.ramp_thread.stop()
            
            self.ramp_thread = ramp(
                self.gate_voltage, 
                target_v, 
                slew_rate=self.slew_rate, 
                param_increment=self.param_increment, 
                min_inter_delay=self.min_inter_delay, 
                verbose=False, 
                blocking=False
            )
        except Exception:
            print("[GATE TEST] An error occurred during ramping.")
            self.ramp_thread.stop()

    def reverse_ramp(self):
        # toggle between index 0 and index 1
        if self.target_idx == 1:
            self.target_idx = 0
        else:
            self.target_idx = 1
        self.start_ramp()

    def poll_instrument(self):
        if self.ramp_thread:
            voltage_V = self.gate_voltage.get()
            current_A = self.gate_current.get()
            self.main.update_plot_data(voltage_V, current_A)
            self.timestamp += 1



if __name__ == "__main__":
    import random
    from qcodes.instrument_drivers.Keithley import Keithley2450

    keithley_1_ip_addr = '192.168.1.30'
    keithley_1_visa_addr = f'TCPIP::{keithley_1_ip_addr}::5025::SOCKET'
    # instantiate and add Keithleys to station 
    keithley_1 = Keithley2450("keithley_1", keithley_1_visa_addr)
    print('Connected to Keithleys.')

    ###
    # set up and alias keithleys
    keithley_1.terminals('front')
    keithley_1.sense.four_wire_measurement(False)
    keithley_1.sense.function('current')
    # set sense range to 100 mA 
    # this sets the internal settling time of the Keithley to something acceptable for remote control
    keithley_1.sense.range(1e-1)
    keithley_1.source.function('voltage')

    # alias sweep params
    V_g = keithley_1.source.voltage
    gate = keithley_1

    
    tester = GateTester(
        gate_voltage_qcodes_param=keithley_1.source.voltage,
        gate_current_qcodes_param=keithley_1.sense.current,
        slew_rate=0.02,             # V/s
        V_range=(-1, 1),           # Min/Max voltage bounds
        param_increment=0.005,       # Voltage step size
        min_inter_delay=0.001       # Delay between steps
    )

    # start app event loops
    tester.run()