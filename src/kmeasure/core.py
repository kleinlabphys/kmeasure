import time
import threading
import numpy as np

def ramp(param, setpoint, slew_rate=0.1, param_increment=0.01, min_inter_delay=0.05, verbose=False, blocking=True):
    '''
    Ramps a QCoDeS parameter (`param`) from its current value to `setpoint` at `slew_rate` in
    steps of `param_increment` with a minimum delay between increments of `min_inter_delay`.
    
    Profile of a ramped parameter looks like a staircase.

    `blocking`=False will run the ramp on a separate thread and return the Thread object

    Args:
    param (QCoDeS parameter): 
    setpoint (parameter unit):
    slew_rate (parameter unit/s):
    param_increment (parameter unit):
    min_inter_delay (s)
    verbose (bool):
    blocking (bool):
    '''

    if slew_rate == 0:
        raise ValueError('[RAMP] ramp slew_rate must not be 0.')
        
    if param_increment == 0:
        raise ValueError('[RAMP] ramp param_increment must not be 0.')

    stop_event = threading.Event()

    def _execute_ramp():
        initial_value = param.get()
        
        step_size = np.abs(setpoint - initial_value)
        N_steps = int(step_size / param_increment)
            
        if N_steps > 1:
            total_T = step_size / slew_rate
            delta_T = total_T / N_steps 
        else:
            param.set(setpoint)
            if verbose:
                print('[RAMP] Finished ramping.')
            return 

        if delta_T < min_inter_delay:
            if verbose:
                print(f'[RAMP] Calculated step time < minimum inter-step delay ({delta_T}<{min_inter_delay}), using minimum delay time instead.') 
            delta_T = min_inter_delay
            
        for next_point in np.linspace(initial_value, setpoint, N_steps):
            
            if stop_event.is_set():
                print("[RAMP] Stopping thread.")
                return # exit function and safely kill thread
            
            time.sleep(delta_T)
            param.set(next_point)

        if verbose:
            print('[RAMP] Finished ramping.')


    if blocking:
        _execute_ramp()
    else:
        # creates a separate thread for the ramp
        # daemonic thread so that external use of this function will auto-kill the thread if the parent thread dies
        ramp_thread = threading.Thread(target=_execute_ramp, daemon=True)
        ramp_thread.stop = stop_event.set
        ramp_thread.start()
        # return the thread object for internal use
        return ramp_thread