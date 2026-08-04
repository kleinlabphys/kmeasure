import sys
import threading
from numbers import Number

import numpy as np

import pyqtgraph as pg
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, Signal

from kmeasure import ramp

class LivePlotter(QtWidgets.QMainWindow):

    spacebar_pressed = Signal()
    escape_pressed = Signal()
    k_pressed = Signal()

    def __init__(self, line_names, num_lines=1):
        super().__init__()

        # anti aliasing
        pg.setConfigOptions(antialias=True)

        # window
        self.setWindowTitle("Live Plotter")

        # Create graph widget
        self.graphWidget = pg.PlotWidget()
        self.setCentralWidget(self.graphWidget)

        # plot style
        self.graphWidget.setBackground('w')
        self.graphWidget.setTitle(f"", color="b", size="16pt")
        self.graphWidget.showGrid(x=True, y=True, alpha=0.3)

        self.legend = self.graphWidget.addLegend(offset=(10, 10))

        # instantiate data buffers
        self.x_data = []
        self.y_data = [[] for _ in range(num_lines)]

        self.data_line = [] 
        self.line_names = line_names

        # line reference
        for i in range(num_lines):
            pen = pg.mkPen(color=pg.intColor(i, hues=num_lines), width=2)
            line = self.graphWidget.plot(self.x_data, self.y_data[i], pen=pen, name=line_names[i])
            self.data_line.append(line)

        self.timer = QtCore.QTimer()
        # Note: 30ms is very fast for sequential VISA socket queries. 
        # If the GUI lags due to the new lock, consider increasing this to ~100.
        self.timer.setInterval(30)
        self.timer.start()

    def update_plot_data(self, new_x_value, dep_param_list):
        self.x_data.append(new_x_value)
        
        for i, param in enumerate(dep_param_list):
            self.y_data[i].append(param)
            self.data_line[i].setData(self.x_data, self.y_data[i])

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            print("escape pressed")
            self.escape_pressed.emit()
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            print("spacebar pressed")
            self.spacebar_pressed.emit()
        elif event.key() == Qt.Key.Key_K:
            print("k pressed")
            self.k_pressed.emit()
        else:
            print(f"Character pressed: {event.text()}")

        super().keyPressEvent(event)

class GateTester:
    def __init__(self, independent_parameter, dependent_parameter_list, slew_rate=0.1, V_range:tuple[Number, Number]=(-10,10), param_increment=0.01, min_inter_delay=0.05):

        self.independent_parameter = independent_parameter
        self.dependent_parameter_list = dependent_parameter_list
        self._apply_thread_safety()

        self.slew_rate = slew_rate
        self.V_range = V_range
        self.param_increment = param_increment
        self.min_inter_delay = min_inter_delay

        # state flags
        self.target_idx = 1 # Start by ramping towards V_range[1]
        self.is_paused = False

        self.timestamp = 0
        self.ramp_thread = None

### This next method is mega gemini-brained

    def _apply_thread_safety(self):
        """
        Safely wraps .set() for independent parameters and .get() for dependent 
        parameters using an RLock to prevent SCPI collisions. Checks method existence 
        to support read-only and write-only parameters.
        """
        self.visa_lock = threading.RLock()

        def wrap_set(param):
            if hasattr(param, "set") and callable(getattr(param, "set", None)):
                if not getattr(param, "_is_set_safe", False):
                    orig_set = param.set
                    def safe_set(*args, _orig=orig_set, **kwargs):
                        with self.visa_lock:
                            return _orig(*args, **kwargs)
                    param.set = safe_set
                    param._is_set_safe = True

        def wrap_get(param):
            if hasattr(param, "get") and callable(getattr(param, "get", None)):
                if not getattr(param, "_is_get_safe", False):
                    orig_get = param.get
                    def safe_get(*args, _orig=orig_get, **kwargs):
                        with self.visa_lock:
                            return _orig(*args, **kwargs)
                    param.get = safe_get
                    param._is_get_safe = True


        wrap_set(self.independent_parameter)
        wrap_get(self.independent_parameter)
        for param in self.dependent_parameter_list:
            wrap_get(param)

    def run(self):
        # prevent crashing if a QApplication already exists
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        
        # pass the amount of dependent parameters to initialize properly
        line_names = [f"{param.full_name} ({param.unit})" for param in self.dependent_parameter_list]
        self.main = LivePlotter(line_names=line_names, num_lines=len(self.dependent_parameter_list))

        self.main.x_data = []
        self.main.y_data = [[] for i in self.dependent_parameter_list]

        # GUI stuff
        self.main.setWindowTitle("Gate Tester")
        self.main.graphWidget.setTitle(f"[SPACE] Change direction   |   [K] Pause   |   [ESC] Close", size="14pt")
        self.main.graphWidget.setLabel('bottom', f"{self.independent_parameter.full_name} ({self.independent_parameter.unit})", color='black', size=16)
        
        # connect signals to controller methods
        self.main.spacebar_pressed.connect(self.reverse_ramp)
        self.main.k_pressed.connect(self.toggle_pause)
        self.main.timer.timeout.connect(self.poll_instrument)

        print("[GATE TEST] Ramping to 0V.")
        # ramp gate to 0V (blocking)
        ramp(
            self.independent_parameter, 
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

            if self.ramp_thread is not None and self.ramp_thread.is_alive():
                self.ramp_thread.stop()
                self.ramp_thread.join()
            
            self.ramp_thread = ramp(
                self.independent_parameter, 
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

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        
        if self.is_paused:
            print("[GATE TEST] Paused.")
            if self.ramp_thread is not None:
                self.ramp_thread.stop()
            self.main.graphWidget.setTitle(f"PAUSED: [SPACE] Change direction   |   [K] Resume   |   [ESC] Close", size="14pt", color="r")
        else:
            print("[GATE TEST] Resuming.")
            self.main.graphWidget.setTitle(f"[SPACE] Change direction   |   [K] Pause   |   [ESC] Close", size="14pt", color="b")
            self.start_ramp()

    def reverse_ramp(self):
        if self.target_idx == 1:
            self.target_idx = 0
        else:
            self.target_idx = 1

        if not self.is_paused:
            self.start_ramp()
        else:
            print(f"[GATE TEST] Direction changed to {self.V_range[self.target_idx]}V, but still paused.")

    def poll_instrument(self):
        if self.ramp_thread:
            # Because we monkey-patched the parameters, these .get() calls
            # are now naturally protected by the threading.Lock
            ind_param = self.independent_parameter.get()
            dep_param_list = [param.get() for param in self.dependent_parameter_list]
            self.main.update_plot_data(ind_param, dep_param_list)
            self.timestamp += 1


# test code
if __name__ == "__main__":
    from qcodes.instrument_drivers.Keithley import Keithley2450

    keithley_1_ip_addr = '192.168.1.30'
    keithley_1_visa_addr = f'TCPIP::{keithley_1_ip_addr}::5025::SOCKET'
    
    # instantiate and add Keithleys to station 
    keithley_1 = Keithley2450("keithley_1", keithley_1_visa_addr)
    print('Connected to Keithleys.')

    keithley_1.terminals('front')
    keithley_1.sense.four_wire_measurement(False)
    keithley_1.sense.function('current')
    
    # set sense range to 100 mA 
    keithley_1.sense.range(1e-1)
    keithley_1.source.function('voltage')

    tester = GateTester(
        independent_parameter=keithley_1.source.voltage,
        dependent_parameter_list=[keithley_1.sense.current, keithley_1.sense.current],
        slew_rate=0.05,             # V/s
        V_range=(-1, 1),           # Min/Max voltage bounds
        param_increment=0.005,       # Voltage step size
        min_inter_delay=0.001       # Delay between steps
    )

    # start app event loops
    tester.run()