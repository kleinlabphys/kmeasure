from qcodes.instrument import Instrument
import socket 

class Manager:
    def __init__(self, host:str='0.0.0.0', port:int=8723):
        self.host = host
        self.port = port

        self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # allows immediate socket reuse

        self.listener_socket.bind((host, port))
        self.listener_socket.listen(1) # allow backlog of 1, i.e. refuse any more than 1 new request to open socket

        self.conn, self.addr = self.listener_socket.accept()

    def ask(self, msg):
        # returns the reply to a message sent by the manager
        formatted_msg = f'{msg}\r\n' ##TODO check if this is actually the format
        try:
            self.conn.send(formatted_msg.encode('utf-8'))
            reply = self.conn.recv(4096).decode('utf-8')
            return reply
        except Exception as e:
            print(f"ERROR while asking: {e}")

    def send(self, msg):
        # manager sends an instruction and does not wait on reply
        formatted_msg = f'{msg}\r\n'
        try:
            self.conn.send(formatted_msg.encode('utf-8'))
            return True
        except Exception as e:
            print(f"ERROR while sending: {e}")

    def close(self):
        # safely closes sockets
        if self.conn:
            try:
                self.conn.shutdown(socket.SHUT_RDWR)
            except socket.error:
                pass
            self.conn.close()
        self.listener_socket.close()
        print('Manager client closed.')

class PPMSClient:
    def __init__(self, manager):
        self.manager = manager

    # for each parameter, define a setter, a general getter, and a getter for each specific returned value
   
    ### magnetic field ###
    def set_field(self, field_setpoint, rate, approach_mode, end_mode):
        """
        field: Field set point in oersted
        
        field_rate: Field ramp rate set point in oersted/second
        
        approach_mode: Approach mode as one of the following codes
        0: Linear
        1: No overshoot
        2: Oscillate
        
        end_mode: Mode at end of field ramp as one of the following codes. 
        0: Persistent
        1: Driven

        I think that the return_code is the state as defined by QD 1070_209.
        """

        # FIELD field_setpoint, rate, approach_mode, end_mode
        # return_code
        msg = f'FIELD {field_setpoint}, {rate}, {approach_mode}, {end_mode}'
        response = self.manager.ask(msg)
        return_code = response.strip()
        return return_code

    @staticmethod
    def _field_status_parser(code) -> str:
        code = str(code).strip()
        
        STATUS_DICT = {
            "0": "Unknown",
            "1": "Persistent" ,
            "2": "Switch warming",
            "3": "Switch cooling",
            "4": "Holding in driven mode",
            "5": "Iterating",
            "6": "Charging",
            "8": "Current error",
            "15": "General failure in field control"
        }

        if code not in ["0", "1", "2", "3", "4", "5", "6", "8", "15"]:
            status = f"Status code {code} not in dictionary"
        else:     
            status = STATUS_DICT[code]

        return status

    def get_all_field_info(self):
        msg = 'FIELD?'
        response = self.manager.ask(msg)
        parts = response.split(",")
        response_list = []

        for part in parts:
            res = part.strip()
            response_list.append(res)

        return_code = int(response_list[0])
        field = float(response_list[1])
        status = self._field_status_parser(response_list[2])

        response_dict = {"return_code":return_code, "field":field, "status":status}
        return response_dict

    def get_field(self):
        response_dict = self.get_all_field_info()
        field = response_dict["field"]
        return field

    def get_field_status(self):
        response_dict = self.get_all_field_info()
        status = response_dict["status"]
        return status

    ### temperature ###
    def set_temp(self, temperature_setpoint, rate, mode):
        """
        temperature: Temperature set point in kelvin

        rate: Temperature rate set point in kelvin/second

        approach: Approach mode as one of the following codes
        0: Fast settle
        1: No overs

        I think that the return_code is the state as defined by QD 1070_209.
        """

        # TEMP temperature_setpoint, rate, mode
        # return_code
        msg = f'TEMP {temperature_setpoint}, {rate}, {mode}'
        response = self.manager.ask(msg)
        return_code = response.strip()
        return return_code

    @staticmethod
    def _temp_status_parser(code) -> str:
        code = str(code).strip()
        STATUS_DICT = {
            "0": "Unknown",
            "1": "Stable",
            "2": "Tracking",
            "5": "Near",
            "6": "Chasing",
            "7": "Filling/emptying reservoir",
            "10": "Standby",
            "15": "General failure in temp control"
        }
        if code not in ["0", "1", "2", "5", "6", "7", "10", "15"]:
            status = f"Status code {code} not in dictionary"
        else:     
            status = STATUS_DICT[code]

        return status

    def get_all_temp_info(self):
        msg = 'TEMP?'
        response = self.manager.ask(msg)
        parts = response.split(",")
        response_list = []

        for part in parts:
            res = part.strip()
            response_list.append(res)

        return_code = int(response_list[0])
        temperature = float(response_list[1])
        status = self._temp_status_parser(response_list[2])

        response_dict = {"return_code":return_code, "temperature":temperature, "status":status}
        return response_dict

    def get_temp(self):
        response_dict = self.get_all_temp_info()
        temp = response_dict["temperature"]
        return temp

    def get_temp_status(self):
        response_dict = self.get_all_temp_info()
        status = response_dict["status"]
        return status

class PPMSInstrument(Instrument):
    def __init__(self, name: str, host:str='0.0.0.0', port:int=8723, **kwargs):
        super().__init__(name, **kwargs)

        self.client = PPMSClient(Manager(host, port))

        # set methods are multi-argument, so we need to store them in the
        # PPMS instrument object.
        # set the defaults below
        self.field_rate = 10.0
        self.field_approach = 0  # 0 = linear
        self.field_end_mode = 0  # 0 = persistent
        
        self.temp_rate = 10.0
        self.temp_mode = 0       # 0 = fast settle
        
        self.add_parameter(
            "field",
            label="Magnetic Field",
            unit="Oe",
            get_cmd=self.client.get_field, 
            set_cmd=self._set_field
        )

        self.add_parameter(
            "field_status",
            label="Magnetic Field Status",
            get_cmd=self.client.get_field_status
        )

        self.add_parameter(
            "temperature",
            label="Temperature",
            unit="K",
            get_cmd=self.client.get_temp,
            set_cmd=self._set_temp
        )

        self.add_parameter(
            "temperature_status",
            label="Temperature Status",
            get_cmd=self.client.get_temp_status
        )

    # custom setter wrappers for the client
    def _set_field(self, field_setpoint:float):
        self.client.set_field(
            field_setpoint, 
            self.field_rate, 
            self.field_approach, 
            self.field_end_mode
        )

    def _set_temp(self, temp_setpoint:float):
        self.client.set_temp(
            temp_setpoint, 
            self.temp_rate, 
            self.temp_mode
        )