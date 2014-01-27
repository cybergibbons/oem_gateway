"""

  This code is released under the GNU Affero General Public License.
  
  OpenEnergyMonitor project:
  http://openenergymonitor.org

"""

import serial
import time, datetime
import logging
import socket, select
import os

"""class OemGatewayListener

Monitors a data source. 

This almost empty class is meant to be inherited by subclasses specific to
their data source.

"""
class OemGatewayListener(object):

    def __init__(self):
        
        # Initialize logger
        self._log = logging.getLogger("OemGateway")
        
    def close(self):
        """Close socket."""
        pass

    def read(self):
        """Read data from socket and process if complete line received.

        Return data as a list: [NodeID, val1, val2]
        
        """
        pass

    def _process_frame(self, f):
        """Process a frame of data

        f (string): 'NodeID val1 val2 ...'

        This function splits the string into integers and checks their 
        validity.

        'NodeID val1 val2 ...' is the generic data format. If the source uses 
        a different format, override this method.
        
        Return data as a list: [NodeID, val1, val2]

        """

        # Log data
        self._log.info("Serial RX: " + f)
        
        # Get an array out of the space separated string
        received = f.strip().split(' ')
        
        # Discard if frame not of the form [node, val1, ...]
        # with number of elements at least 2
        if (len(received) < 2):
            self._log.warning("Misformed RX frame: " + str(received))
        
        # Else, process frame
        else:
            try:
                received = [int(val) for val in received]
            except Exception:
                self._log.warning("Misformed RX frame: " + str(received))
            else:
                self._log.debug("Node: " + str(received[0]))
                self._log.debug("Values: " + str(received[1:]))
                return received
    
    def set(self, **kwargs):
        """Set configuration parameters.

        **kwargs (dict): settings to be sent. Example:
        {'setting_1': 'value_1', 'setting_2': 'value_2'}
        
        """
        pass

    def run(self):
        """Placeholder for background tasks. 
        
        Allows subclasses to specify actions that need to be done on a 
        regular basis. This should be called in main loop by instantiater.
        
        """
        pass

    def _open_serial_port(self, com_port):
        """Open serial port

        com_port (string): path to COM port

        """
        
        self._log.debug('Opening serial port: %s', com_port)
        
        try:
            s = serial.Serial(com_port, 9600, timeout = 0)
        except serial.SerialException as e:
            self._log.error(e)
            raise OemGatewayListenerInitError('Could not open COM port %s' %
                                              com_port)
        else:
            return s
    
    def _open_socket(self, port_nb):
        """Open a socket

        port_nb (string): port number on which to open the socket

        """

        self._log.debug('Opening socket on port %s', port_nb)
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', int(port_nb)))
            s.listen(1)
        except socket.error as e:
            self._log.error(e)
            raise OemGatewayListenerInitError('Could not open port %s' %
                                            port_nb)
        else:
            return s

"""class OemGatewaySerialListener

Monitors the serial port for data

"""
class OemGatewaySerialListener(OemGatewayListener):

    def __init__(self, com_port):
        """Initialize listener

        com_port (string): path to COM port

        """
        
        # Initialization
        super(OemGatewaySerialListener, self).__init__()

        # Open serial port
        self._ser = self._open_serial_port(com_port)
        
        # Initialize RX buffer
        self._rx_buf = ''

    def close(self):
        """Close socket."""
        
        # Close serial port
        if self._ser is not None:
            self._log.debug("Closing serial port.")
            self._ser.close()

    def read(self):
        """Read data from serial port and process if complete line received.

        Return data as a list: [NodeID, val1, val2]
        
        """
        
        # Read serial RX
        self._rx_buf = self._rx_buf + self._ser.readline()
        
        # If line incomplete, exit
        if '\r\n' not in self._rx_buf:
            return

        # Remove CR,LF
        f = self._rx_buf[:-2]

        # Reset buffer
        self._rx_buf = ''

        # Process data frame
        return self._process_frame(f)

"""class OemGatewayRFM2PiListener

Monitors the serial port for data from RFM2Pi

"""
class OemGatewayRFM2PiListener(OemGatewaySerialListener):

    def __init__(self, com_port):
        """Initialize listener

        com_port (string): path to COM port

        """
        
        # Initialization
        super(OemGatewayRFM2PiListener, self).__init__(com_port)

        # Initialize settings
        self._settings = {'baseid': '', 'frequency': '', 'sgroup': '', 
            'sendtimeinterval': ''}
        
        # Initialize time updata timestamp
        self._time_update_timestamp = 0

    def _process_frame(self, f):
        """Process a frame of data

        f (string): 'NodeID val1_lsb val1_msb val2_lsb val2_msb ...'

        This function recombines the integers and checks their validity.
        
        Return data as a list: [NodeID, val1, val2]

        """
        
        # Log data
        self._log.info("Serial RX: " + f)
        
        # Get an array out of the space separated string
        received = f.strip().split(' ')
        
        # If information message, discard
        if ((received[0] == '>') or (received[0] == '->')):
            return

        # Else, discard if frame not of the form 
        # [node val1_lsb val1_msb val2_lsb val2_msb ...]
        # with number of elements odd and at least 3
        elif ((not (len(received) & 1)) or (len(received) < 3)):
            self._log.warning("Misformed RX frame: " + str(received))
        
        # Else, process frame
        else:
            try:
                received = [int(val) for val in received]
            except Exception:
                self._log.warning("Misformed RX frame: " + str(received))
            else:
                # Get node ID
                node = received[0]
                
                # Recombine transmitted chars into signed int
                values = []
                for i in range(1, len(received),2):
                    value = received[i] + 256 * received[i+1]
                    if value > 32768:
                        value -= 65536
                    values.append(value)
                
                self._log.debug("Node: " + str(node))
                self._log.debug("Values: " + str(values))
    
                # Insert node ID before data
                values.insert(0, node)

                return values

    def set(self, **kwargs):
        """Send configuration parameters to the RFM2Pi through COM port.

        **kwargs (dict): settings to be modified. Available settings are
        'baseid', 'frequency', 'sgroup'. Example: 
        {'baseid': '15', 'frequency': '4', 'sgroup': '210'}
        
        """
        
        for key, value in kwargs.iteritems():
            # If radio setting modified, transmit on serial link
            if key in ['baseid', 'frequency', 'sgroup']:
                if value != self._settings[key]:
                    self._settings[key] = value
                    self._log.info("Setting RFM2Pi | %s: %s" % (key, value))
                    string = value
                    if key == 'baseid':
                        string += 'i'
                    elif key == 'frequency':
                        string += 'b'
                    elif key == 'sgroup':
                        string += 'g'
                    self._ser.write(string)
                    # Wait a sec between two settings
                    time.sleep(1)
            elif key == 'sendtimeinterval':
                if value != self._settings[key]:
                    self._log.info("Setting send time interval to %s", value)
                    self._settings[key] = value

    def run(self):
        """Actions that need to be done on a regular basis. 
        
        This should be called in main loop by instantiater.
        
        """

        now = time.time()

        # Broadcast time to synchronize emonGLCD
        interval = int(self._settings['sendtimeinterval'])
        if (interval): # A value of 0 means don't do anything
            if (now - self._time_update_timestamp > interval):
                self._send_time()
                self._time_update_timestamp = now
    
    def _send_time(self):
        """Send time over radio link to synchronize emonGLCD.

        The radio module can be used to broadcast time, which is useful
        to synchronize emonGLCD in particular.
        Beware, this is know to garble the serial link on RFM2Piv1
        sendtimeinterval defines the interval in seconds between two time
        broadcasts. 0 means never.

        """

        now = datetime.datetime.now()

        self._log.debug("Broadcasting time: %d:%d" % (now.hour, now.minute))

        self._ser.write("00,%02d,%02d,00,s" % (now.hour, now.minute))

class OemGatewayOWFSListener(OemGatewayListener):

    def __init__(self, **kwargs):

        super(OemGatewayOWFSListener, self).__init__()

        # Default OWFS path
        self._path = '/mnt/1wire'

        # emonTX defaults to 10
        # 0 reserved
        # 1-4 control nodes
        # 5-10 energy monitoring nodes
        # 11-14 unassigned
        # 15-16 base station nodes
        # 17-30 environmental sensing nodes
        # 31 reserved
        self._node = '9'

        # temperature nodes send every minute
        self._interval = 60

        # how many bits of resolution should we read DS18B20
        self._resolution = 9

        for key, value in kwargs.iteritems():
            if key == 'path':
                if os.access(value, os.R_OK):
                    self._path = value
                else:
                    raise OemGatewayListenerInitError('OWFS path not valid')

            if key == 'node':
                node = int(value)
                if 0 < node < 31:
                    self._node = node
                else:
                    raise OemGatewayListenerInitError('Node must be between 1 and 30')

            if key == 'interval':
                self._interval = int(value)

            if key == 'resolution':
                if int(value) in [9, 10, 11, 12]:
                    self._resolution = int(value)
                else:
                    raise OemGatewayListenerInitError('Resolution must be 9, 10, 11 or 12')

        self._read_timestamp = 0

        self._sensors = []

        self._log.info('Initialising OWFS listener in %s', self._path)
        self._log.info('Node ID: %s sending every %ss', self._node, self._interval)

    def set(self, **kwargs):
        self._sensors = []
        # Sort by the key ('sensorX') and then add to a list
        for key in sorted(kwargs.iterkeys()):
            if key.startswith('sensor'):
                self._sensors.append(kwargs[key])

        self._log.info('Added %s sensors', len(self._sensors))

        for sensor_id in self._sensors:
            self._log.debug('Sensor ID: %s', sensor_id)

    def read(self):

        now = time.time()

        if now - self._read_timestamp > self._interval:
            self._log.info('Reading OWFS in %s', self._path)

            self._read_timestamp = now

            received = [self._node]

            for sensor_id in self._sensors:
                temperature = None

                # We allow dummy sensors - this means that indexing of real sensors is preserved
                if sensor_id.lower() != 'dummy':
                    # A real sensor ID
                    self._log.debug('%s reading', sensor_id)

                    if sensor_id in os.listdir(self._path):

                        path = os.path.join(self._path, sensor_id, 'temperature' + str(self._resolution))

                        try:
                            f = open(path)
                            temperature = f.readline().strip()
                            f.close()
                        except IOError:
                            self._log.warning('%s unable to read temperature', sensor_id)

                        self._log.debug('%s read %sC', sensor_id, temperature)

                    else:
                        self._log.debug('%s sensor does not exist', sensor_id)

                else:
                    # Allow dummy sensor IDs
                    self._log.debug('Skipping dummy sensor')

                # Return as a list of temperatures where dummy or unreadable = None
                received.append(temperature)

            return received

        return


"""class OemGatewaySocketListener

Monitors a socket for data, typically from ethernet link

"""
class OemGatewaySocketListener(OemGatewayListener):

    def __init__(self, port_nb):
        """Initialize listener

        port_nb (string): port number on which to open the socket

        """
 
        # Initialization
        super(OemGatewaySocketListener, self).__init__()

        # Open socket
        self._socket = self._open_socket(port_nb)

        # Initialize RX buffer for socket
        self._sock_rx_buf = ''

    def close(self):
        """Close socket."""
        
        # Close socket
        if self._socket is not None:
           self._log.debug('Closing socket')
           self._socket.close()

    def read(self):
        """Read data from socket and process if complete line received.

        Return data as a list: [NodeID, val1, val2]
        
        """
        
        # Check if data received
        ready_to_read, ready_to_write, in_error = \
            select.select([self._socket], [], [], 0)

        # If data received, add it to socket RX buffer
        if self._socket in ready_to_read:

            # Accept connection
            conn, addr = self._socket.accept()
            
            # Read data
            self._sock_rx_buf = self._sock_rx_buf + conn.recv(1024)
            
            # Close connection
            conn.close()

        # If there is at least one complete frame in the buffer
        if '\r\n' in self._sock_rx_buf:
            
            # Process and return first frame in buffer:
            f, self._sock_rx_buf = self._sock_rx_buf.split('\r\n', 1)
            return self._process_frame(f)

"""class OemGatewayRFM2PiListenerRepeater

Monitors the serial port for data from RFM2Pi, 
and repeats on RF link the frames received through a socket

"""
class OemGatewayRFM2PiListenerRepeater(OemGatewayRFM2PiListener):

    def __init__(self, com_port, port_nb):
        """Initialize listener

        com_port (string): path to COM port
        port_nb (string): port number on which to open the socket

        """
        
        # Initialization
        super(OemGatewayRFM2PiListenerRepeater, self).__init__(com_port)

        # Open socket
        self._socket = self._open_socket(port_nb)
        
        # Initialize RX buffer for socket
        self._sock_rx_buf = ''

    def run(self):
        """Monitor socket and repeat data if complete frame received."""

        # Execute run() method from parent
        super(OemGatewayRFM2PiListenerRepeater, self).run()
                        
        # Check if data received on socket
        ready_to_read, ready_to_write, in_error = \
        select.select([self._socket], [], [], 0)

        # If data received, add it to socket RX buffer
        if self._socket in ready_to_read:

            # Accept connection
            conn, addr = self._socket.accept()
                                                                                                                        
            # Read data
            self._sock_rx_buf = self._sock_rx_buf + conn.recv(1024)
            
            # Close connection
            conn.close()

        # If there is at least one complete frame in the buffer
        if '\r\n' in self._sock_rx_buf:
            
            # Send first frame in buffer:
            f, self._sock_rx_buf = self._sock_rx_buf.split('\r\n', 1)
            self._log.info("Sending frame: %s", f)
            self._ser.write(f)

"""class OemGatewayListenerInitError

Raise this when init fails.

"""
class OemGatewayListenerInitError(Exception):
    pass

