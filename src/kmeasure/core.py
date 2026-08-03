import time
from numpy import np

def ramp(param, setpoint, slew_rate=0.1, param_increment=0.01, min_inter_delay=0.05, verbose=False):
    '''
    Ramps a QCoDeS parameter (`param`) from its current value to `setpoint` at `slew_rate` in
    steps of `param_increment` with a minimum delay between increments of `min_inter_delay`.
    
    Profile of a ramped parameter looks like a staircase.

    Args:
    param (QCoDeS parameter): 
    setpoint (parameter unit):
    slew_rate (parameter unit/s):
    param_increment (parameter unit):
    min_inter_delay (s)
    '''
    initial_value = param.get()
    
    step_size = np.abs(setpoint - initial_value)
    N_steps = int(step_size / param_increment)

    if slew_rate == 0:
        raise Exception('[RAMP] ramp slew_rate must not be 0.')
        
    if param_increment == 0:
        raise Exception('[RAMP] ramp param_increment must not be 0.')
        
    if N_steps > 1:
        total_T = step_size / slew_rate
        delta_T = total_T / N_steps 
    else:
        param.set(setpoint)
        if verbose:
            print('Already at setpoint')
       # print(f'RAMP: Ramp unnecessary, setting [{param}={setpoint}] directly.')
        return 

    if delta_T < min_inter_delay:
        print(f'[RAMP] Calculated step time < minimum inter-step delay ({delta_T}<{min_inter_delay}), using minimum delay time instead.') 
        delta_T = min_inter_delay
        
    for next_point in np.linspace(initial_value, setpoint, N_steps):
        time.sleep(delta_T)
        param.set(next_point)
        # print(next_point)

    if verbose:
        print('done ramping')