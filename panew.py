#!/usr/bin/env python

from __future__ import division, print_function
import argparse
import re
import sys
import subprocess

class PIDController(object):
    def __init__(self, Kp, Ki, Kd, setpoint=0):
        self.setpoint = setpoint
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.integral = 0
        self._previous_error = 0
        self._change_limit = 0

    def input_change(self, process_feedback, dt):
        """ Calculates desired input value change.
        
            Based on process feedback and time inteval (dt)."""
        error = self.setpoint - process_feedback
        self.integral = self.integral + (error * dt)
        derivative = (error - self._previous_error) / dt
        self._previous_error = error
        input_change = (self.Kp * error) + \
               (self.Ki * self.integral) + \
               (self.Kd * derivative)
        if self._change_limit and abs(input_change) > abs(self._change_limit):
            sign = input_change / abs(input_change)
            input_change = sign * self._change_limit
        return input_change

    def set_change_limit(self, limit):
        """Ensures that input value changes are lower than limit.
        
           Setting limit of zero disables this. """
        self._change_limit = limit


class PAVolumeController(object):
    pa_types={'input': 'source', 'output': 'sink'}

    def __init__(self, type, method = None):
        """Initializes the volume controller.

           Arguments:
           type: either input or output
           method: a method that will run a command and return pulseaudio
           information in the described format, as a single string with
           line breaks (to be processed with str.splitlines())

        """

        self.type = type
        self._volume = None
        self.identifier = None
        self.method = method
        if not callable(method):
            self.method = self._pactl_output

    def set(self, volume):
        if not 0 <= volume <= 100:
            return False
        if not self.identifier:
            return False
        command = ['pactl', 
                   'set-%s-volume' % (self.pa_types[self.type]), 
                   str(self.identifier[0]),
                   str(volume)]
        if not self.method(command):
            return False
        self._volume = volume
        return True

    def get(self):
        if not self.identifier:
            return None
        return self._volume

    def get_identifier(self):
        if self.type:
            self.identifier = self._get_identifier_for(self.type)
            return self.identifier
            

    def _get_identifier_for(self, type):
        """Gets default PulseAudio identifier for given type.

           Arguments:
           type: either input or output

           Returns:
           A tuple: (pa_id, pa_description)

        """

        if type not in self.pa_types:
            return None 
        command = ['pactl', 'list', self.pa_types[type] + "s", 'short']

        #Expect lines of this form (field separator is tab):
        #<ID>\t<NAME>\t<MODULE>\t<SAMPLE_SPEC_WITH_SPACES>\t<STATE>
        #What we need to return is the ID for the first element on this list
        #that does not contain auto_null or monitor.
        pa_info = self.method(command)

        valid_elements=[(int(i.split()[0]), i.split()[1]) \
                        for i in pa_info.splitlines() \
                        if not re.match('.*monitor.*', i) \
                        and not re.match('.*auto_null.*', i)]
        if not valid_elements:
            return None
        return valid_elements[0]

    def _pactl_output(self, command):
        try:
            return subprocess.check_output(command, universal_newlines = True)
        except subprocess.CalledProcessError:
            return False


class SpectrumAnalyzer(object):
    def __init__(self):
        self.spectrum = []

    def sample(self, sample):
        #WATCH IT if we're starting with an empty self.spectrum.
        #DEFINE behavior if arrays are of diff size.
        self.spectrum = [sum(a) for a in zip(self.spectrum, sample)]





#
def main():
    #Get arguments.
    #Launches recording pipeline. I need to hook up into the gst
    #messages. 
    recorder = Recorder()
    #Just launches the playing pipeline 
    player = Player()
    #Handles most of the time-dependent logic:
    # - On 'level' messages, sends feedback to the pidctrl and sets volume
    # accordingly.
    # - On 'spectrum' messages, gets spectrum magnitudes and feeds them into the
    # analyzer, ONLY if the data is adequate (not over the setpoint)
    #
    gmh = GStreamerMessageHandler()
    #This just receives a process feedback and tells me how much to change to 
    #achieve the setpoint
    pidctrl = PIDController(Kp=0.1, Ki=0.1, Kd=0.1, setpoint=-2.0)
    #This  gathers spectrum data. Should be able to do the frequency band analysis.
    analyzer = SpectrumAnalyzer()
    #Volume controllers actually set volumes for their device types.
    recorder.volumecontroller=PAVolumeController(type='input')
    player.volumecontroller=PAVolumeController(type='output')
    #I need to tell the recorder which method will handle messages.
    recorder.register_handler(gmh.handler)
   
    #Set default volumes
    recorder.volumecontroller.set(0)
    player.volumecontroller.set(50)

    #Start the loops

    #When the loops exit, see if data gathering was successful.


