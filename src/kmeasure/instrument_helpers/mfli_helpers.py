from qcodes.parameters import MultiParameter
import numpy as np

class MFLIDemodPoller(MultiParameter):
    def __init__(self, name, zi_session, device, poll_time, timeout=10, demod_channel=0):
        super().__init__(
            name,
            names = ('poll_timestamp','x','y','frequency','phase','dio','auxin0','auxin1'),
            shapes = ((),(),(),(),(),(),(),()),
            labels = ('poll_timestamp','x','y','frequency','phase','dio','auxin0','auxin1'),
            setpoints = ((),(),(),(),(),(),(),()),
            docstring = "QCoDeS friendly wrapper for zhinst poll method. Polls demod 'device' and for poll_param. "
        )
        self.zi_session = zi_session
        self.device = device
        self.demod_channel = demod_channel
        self.timeout = timeout
        self.poll_time = poll_time
        
    def get_raw(self):
        zi_session = self.zi_session
        device = self.device
        demod_channel = self.demod_channel
        poll_time = self.poll_time
        timeout = self.timeout
        device.demods[demod_channel].sample.subscribe()
        data = zi_session.poll(poll_time, timeout)
        device.demods[demod_channel].sample.unsubscribe()

        sample_key = list(data.keys())[0]
        sample = data[sample_key]

        timestamp = np.mean(sample['timestamp'])
        x = np.mean(sample['x'])
        y = np.mean(sample['y'])
        frequency = np.mean(sample['frequency'])
        phase = np.mean(sample['phase'])
        dio = np.mean(sample['dio'])
        auxin0 = np.mean(sample['auxin0'])
        auxin1 = np.mean(sample['auxin1'])

        return (
            timestamp,
            x,
            y,
            frequency,
            phase,
            dio,
            auxin0,
            auxin1
        )