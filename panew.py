#!/usr/bin/env python

from __future__ import division, print_function
import argparse
import collections
import logging
import math
import re
import sys
import subprocess
try:
    import gobject
    import gst
    import subprocess
    from glib import GError
except ImportError:
    print("Can't import module: %s. it may not be available for this"
          "version of Python, which is: " % sys.exc_info()[1], file=sys.stderr)
    print((sys.version), file=sys.stderr)
    sys.exit(127)


#Frequency bands for FFT
BINS = 256 
#How often to take a sample and do FFT on it.
FFT_INTERVAL = 100000000 #In nanoseconds, so this is every 1/10th second
#Sampling frequency. The effective maximum frequency we can analyze is
#half of this (see Nyquist's theorem)
SAMPLING_FREQUENCY = 44100 
#The default test frequency should be in the middle of the frequency band
#that delimits the first and second thirds of the frequency range.
#That gives a not-so-ear-piercing tone and should ensure there's no
#spillout to neighboring frequency bands.
DEFAULT_TEST_FREQUENCY = (SAMPLING_FREQUENCY * BINS) / (6 * BINS) + \
                         (SAMPLING_FREQUENCY / (2 * BINS))
#only sample a signal when peak level is in this range (in dB attenuation,
#0 means no attenuation (and horrible clipping).
REC_LEVEL_RANGE = (-2.0, -10)
#For our test signal to be considered present, it has to be this much higher
#than the average of the rest of the frequencies (to ensure we have a nice,
#clear peak). This is in dB.
MAGNITUDE_THRESHOLD = -5.0


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

    def __init__(self, type, method = None, logger=None):
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
        if not isinstance(method, collections.Callable):
            self.method = self._pactl_output
        self.logger = logger

    def set(self, volume):
        if not 0 <= volume <= 100:
            return False
        if not self.identifier:
            return False
        command = ['pactl', 
                   'set-%s-volume' % (self.pa_types[self.type]), 
                   str(self.identifier[0]),
                   str(int(volume))+"%"]
        if False == self.method(command):
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
            if self.identifier and self.logger:
                message = "Using PulseAudio identifier %s (%s) for %s" %\
                       (self.identifier +  (self.type,))
                self.logger.info(message)
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
            if self.logger: self.logger.error("No valid PulseAudio elements"
                                                " for %s" % (self.type))
            return None
        return valid_elements[0]

    def _pactl_output(self, command):
        try:
            return subprocess.check_output(command, universal_newlines = True)
        except subprocess.CalledProcessError:
            return False


class SpectrumAnalyzer(object):
    def __init__(self, points, sampling_frequency=44100):
        self.spectrum = [0] * points
        self.number_of_samples = 0
        self.sampling_frequency = sampling_frequency
        #Frequencies should contain *real* frequency which is half of
        #the sampling frequency
        self.frequencies = [((sampling_frequency / 2.0) / points) * i 
                            for i in range(points)]

    def _average(self):
        return sum(self.spectrum) / len(self.spectrum)

    def sample(self, sample):
        if len(sample) != len(self.spectrum): 
            return
        self.spectrum = [((old * self.number_of_samples) + new) /
                         (self.number_of_samples + 1)
                         for old, new in zip(self.spectrum, sample)]
        self.number_of_samples += 1

    def frequencies_over_average(self, threshold=0.0):
        return [i for i in range(len(self.spectrum)) if self.spectrum[i] >= self._average() - threshold]

    def frequency_band_for(self, frequency):
        """Convenience function to tell me which band
           a frequency is contained in"""
        #Note that actual frequencies are half of what the sampling
        #frequency would tell us. If SF is 44100 then maximum actual
        #frequency is 22050, and if I have 10 frequency bins each will
        #contain only 2205 Hz, not 4410 Hz. 
        max_frequency = self.sampling_frequency / 2
        if frequency > max_frequency or frequency < 0 :
            return None
        band = float(frequency) / (max_frequency / len(self.spectrum))
        return int(math.ceil(band)) - 1 

    def frequencies_for_band(self, band):
        """Convenience function to tell me the delimiting frequencies
          for a band"""
        if band >= len(self.spectrum) or band < 0:
            return None
        lower = self.frequencies[band] 
        upper = lower + ((self.sampling_frequency / 2.0) / len(self.spectrum))
        return (lower, upper)


class GStreamerMessageHandler(object):
    def __init__(self, rec_level_range, logger, volumecontroller,
                 pidcontroller, spectrum_analyzer):
        """Initializes the message handler. It knows how to handle
           spectrum and level gstreamer messages.

           Arguments:
           rec_level_range: tuple with acceptable recording level
                            ranges
           logger: logging object with debug, info, error methods.
           volumecontroller: an instance of VolumeController to use
                             to adjust RECORDING level
           pidcontroller: a PID controller instance which helps control
                          volume
           spectrum_analyzer: instance of SpectrumAnalyzer to collect
                              data from spectrum messages
           
        """
        self.current_level = sys.maxsize
        self.logger = logger
        self.pid_controller = pidcontroller
        self.rec_level_range = rec_level_range
        self.spectrum_analyzer = spectrum_analyzer
        self.volume_controller = volumecontroller

    def bus_message_handler(self, bus, message):
        if message.type == gst.MESSAGE_ELEMENT:
            message_name = message.structure.get_name()
            if message.structure.get_name() == 'spectrum' :
                #First check that the data is adequate (who can tell us that?)
                fft_magnitudes = message.structure['magnitude'] 
                self.spectrum_method(self.spectrum_analyzer, fft_magnitudes) 

            if message.structure.get_name() == 'level':
                #peak_value is our process feedback
                peak_value = message.structure['peak'][0]
                self.level_method(peak_value, self.pid_controller, self.volume_controller) 

                #invoke PIDController's input method
                #get the desired control input value
                #apply that to recorder's pavolumecontroller
        
    #Adjust recording level
    def level_method(self, level, pid_controller, volume_controller):
        #If volume controller doesn't return a valid volume, 
        #we can't control it :(
        current_volume = volume_controller.get()
        if current_volume == None:
            self.logger.error("Unable to control recording volume."
                          "Test results may be wrong")
            return
        self.current_level = level
        change = pid_controller.input_change(level, 0.10)
        logging.debug("level: %s, change: %d, volume: %d" % 
                (level, change, current_volume))
        volume_controller.set(current_volume + change)

    #Only sample if level is within the threshold
    def spectrum_method(self, analyzer, spectrum):
        if self.rec_level_range[1] <= self.current_level <= self.rec_level_range[0]:
            self.logger.debug("Sampling, recorded %d samples" % analyzer.number_of_samples)
            analyzer.sample(spectrum)
            #If I've collected a certain number of samples, send a signal
            #that should stop the process now.


class GstAudioObject(object):
    def __init__(self):
        self.class_name = self.__class__.__name__

    def _set_state(self, state, description):
        self.pipeline.set_state(state)
        message="%s: %s" % (self.class_name, description)
        if self.logger: self.logger.info(message)

    def start(self):
        self._set_state(gst.STATE_PLAYING, "Starting")

    def stop(self):
        self._set_state(gst.STATE_NULL, "Stopping")


class Player(GstAudioObject):
    def __init__(self, frequency=DEFAULT_TEST_FREQUENCY, logger=None):
        super(Player, self).__init__()
        self.pipeline_description = ("audiotestsrc wave=sine freq=%s "
                                "! audioconvert "
                                "! audioresample "
                                "! autoaudiosink" % int(frequency))
        self.logger = logger
        if self.logger: self.logger.debug(self.pipeline_description)
        self.pipeline = gst.parse_launch(self.pipeline_description)


class Recorder(GstAudioObject):
    def __init__(self, bins=BINS, sampling_frequency=SAMPLING_FREQUENCY,
                 fft_interval=FFT_INTERVAL, logger=None):
        super(Recorder, self).__init__()
        pipeline_description=('''autoaudiosrc name=recordersrc
        ! queue
        ! level message=true name=recorderlevel
        ! audioconvert
        ! audio/x-raw-int,channels=1, rate=%(rate)s
        ! audioresample
        ! spectrum interval=%(fft_interval)s bands = %(bands)s
        ! wavenc
        ! appsink name=recordersink emit-signals=true''' %
        {'bands': bins,
         'rate': sampling_frequency,
         'fft_interval': fft_interval} )
        self.logger = logger
        if self.logger: self.logger.debug(pipeline_description)
        self.pipeline = gst.parse_launch(pipeline_description)

    def register_message_handler(self, handler_method):
        if self.logger:
            message="Registering message handler: %s" % handler_method
            self.logger.debug(message)
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message', handler_method)

    def register_buffer_handler(self, handler_method):
        if self.logger:
            message="Registering buffer handler: %s" % handler_method
            self.logger.debug(message)
        self.sink = self.pipeline.get_by_name('recordersink')
        self.sink.connect('new-buffer', handler_method)


def process_arguments():
    description = """
    Plays a single frequency through the default output,
    then records on the default input device. Analyzes the
    recorded signal to test for presence of the played frequency,
    if present it exits with success.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("-t", "--time",
            dest='test_duration',
            action='store',
            default=30,
            type=int,
            help="""Maximum test duration, default %(default)s seconds.
                    Test will exit sooner if it determines it has enough data.""")
    parser.add_argument("-a", "--audio",
            action='store',
            default=None,
            type=str,
            help="File to save recorded audio in .wav format")
    parser.add_argument("-v", "--verbose",
            action='store_true',
            default=False,
            help="Be verbose")
    parser.add_argument("-d", "--debug",
            action='store_true',
            default=False,
            help="Debugging output")
    parser.add_argument("-f", "--frequency",
            action='store',
            default=DEFAULT_TEST_FREQUENCY,
            type=int,
            help="Frequency for test signal, default %(default)s Hz")
    parser.add_argument("-u", "--spectrum",
            action='store',
            type=str,
            help="""File to save spectrum information for plotting
                    (one frequency/magnitude pair per line)""")
    return parser.parse_args()


#
def main():
    #Get arguments.
    args = process_arguments()

    #Setup logging
    level = logging.ERROR
    if args.debug:
        level = logging.DEBUG
    if args.verbose:
        level = logging.INFO
    logging.basicConfig(level=level) 
    #Launches recording pipeline. I need to hook up into the gst
    #messages. 
    recorder = Recorder(logger=logging)
    #Just launches the playing pipeline 
    player = Player(frequency=args.frequency, logger=logging)
    #This just receives a process feedback and tells me how much to change to 
    #achieve the setpoint
    pidctrl = PIDController(Kp=1.0, Ki=.01, Kd=0.01, setpoint=REC_LEVEL_RANGE[0])
    pidctrl.set_change_limit(10)
    #This  gathers spectrum data. Should be able to do the 
    #frequency band analysis.
    analyzer = SpectrumAnalyzer(points=BINS, sampling_frequency=SAMPLING_FREQUENCY)
    #Handles most of the time-dependent logic:
    # - On 'level' messages, sends feedback to the pidctrl and sets volume
    # accordingly.
    # - On 'spectrum' messages, gets spectrum magnitudes and #
    # feeds them into the analyzer, ONLY if the data is adequate 
    # (not over the setpoint)

    #Volume controllers actually set volumes for their device types.
    recorder.volumecontroller=PAVolumeController(type='input', logger = logging)
    recorder.volumecontroller.get_identifier()
    recorder.volumecontroller.set(0)

    player.volumecontroller=PAVolumeController(type='output', logger = logging)
    player.volumecontroller.get_identifier()
    player.volumecontroller.set(30)

    gmh = GStreamerMessageHandler(rec_level_range=REC_LEVEL_RANGE, 
                                  logger=logging, 
                                  volumecontroller=recorder.volumecontroller,
                                  pidcontroller=pidctrl,
                                  spectrum_analyzer=analyzer)

    #I need to tell the recorder which method will handle messages.
    recorder.register_message_handler(gmh.bus_message_handler)

    #Start the loops
    gobject.threads_init()
    loop = gobject.MainLoop()
    gobject.timeout_add_seconds(0, player.start)
    gobject.timeout_add_seconds(0, recorder.start)
    gobject.timeout_add_seconds(args.test_duration, loop.quit)
    loop.run()

    #Stop elements.
    player.stop()
    recorder.stop()
    player.volumecontroller.set(50)
    recorder.volumecontroller.set(10)

    #When the loops exit, see if data gathering was successful.
    test_band = analyzer.frequency_band_for(args.frequency)
    candidate_bands = analyzer.frequencies_over_average(MAGNITUDE_THRESHOLD)
    if test_band in candidate_bands :
        freqs_for_band = analyzer.frequencies_for_band(test_band)
        print("PASS: Test frequency of %s in band (%.2f, %.2f) "
              "which had a magnitude higher than the average" %
            ((args.frequency,) + freqs_for_band))
        return_value = 0
    else:
        print("FAIL: Test frequency of %s is not in one of the "
              "bands with higher-than-average magnitude" % args.frequency )
        return_value = 1

    return return_value
    

if __name__ == "__main__":
    sys.exit(main())
