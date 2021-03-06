#!/usr/bin/env python
# This script outputs a test frequency through the default audio device
# (either speakers or headphone), and records audio from the default input
# device (either microphone or line-in). It automatically adjusts recording
# level so it's as high as possible without clipping or saturating.
#
# When it's within this recording level range, it takes the frequency
# components of the recorded audio to determine which frequencies are present.
# It will record until it has 2 seconds' worth of usable frequency data.
# If the test frequency is present (meaning it recorded what was played),
# the test passes. Otherwise it fails.
#
# The test frequency, maximum test duration, and files to output the
# recorded wave and frequency analysis (for later validation) can be specified
# on the command-line.
#
# The test works best when the test frequency is higher than likely frequencies
# for ambient noise; setting it to 1500 Hz or above should work. The
# default test frequency is chosen with this in mind.

from __future__ import division, print_function
import argparse
import re
import sys

#How many frequency bands to use
BINS = 256 
FFT_INTERVAL = 100000000 #In nanoseconds, so this is every 1/10th second
#Sampling frequency. The effective maximum frequency we can analyze is
#half of this (see Nyquist's theorem)
SAMPLING_FREQUENCY = 44100 
#Aim for this level of attenuation for the volume control in dB.
REC_LEVEL = -2.0
#For our test signal to be considered present, it has to be this much higher
#than the average of the rest of the frequencies (to ensure we have a nice,
#clear peak). This is in dB.
MAGNITUDE_THRESHOLD = 5.0
#The default test frequency should be in the middle of the frequency band
#that delimits the first and second thirds of the frequency range.
#That gives a not-so-ear-piercing tone and should ensure there's no
#spillout to neighboring frequency bands.
DEFAULT_TEST_FREQUENCY = (SAMPLING_FREQUENCY * BINS) / (6 * BINS) + \
                         (SAMPLING_FREQUENCY / (2 * BINS))


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
args = parser.parse_args()

#import rest of the modules; specifically, gst, because otherwise
#it interferes with argument processing.

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


class AudioObject(object):
    def __init__(self):
        self.pactl_identification = None

    def start(self):
        self.pipeline.set_state(gst.STATE_PLAYING)

    def stop(self):
        self.pipeline.set_state(gst.STATE_NULL)
        self.volumecontrol(self.default_volume)

    def volumecontrol(self, volume):
        if self.audio_type not in ['source', 'sink']:
            return
        if not self.pactl_identification:
            self.pactl_identification = \
                    self.get_pactl_id_for_default(self.audio_type)
            if self.pactl_identification:
                if self.verbose:
                    print("Using %s to control %s volume" % 
                          (self.pactl_identification[1], self.audio_type))
            else:
                print("I couldn't get a reasonable %s identifier. "
                      "Test will probably fail." % self.audio_type)

        if self.pactl_identification:
            if not self.pactl_command('set-%s-volume' % self.audio_type, 
                           self.pactl_identification[0], 
                           volume):
                print("Unable to set %s volume to %s" %
                        (self.audio_type, volume))

    def get_pactl_id_for_default(self, type):
        if not type in ['source', 'sink']:
            return None
        type += 's'
        element_list = subprocess.check_output(['pactl',
                                                'list',
                                                type,
                                                'short'], 
                                                universal_newlines = True)
        valid_elements=[(int(i.split()[0]), i.split()[1]) \
                        for i in element_list.splitlines() \
                        if not re.match('.*monitor.*', i) \
                        and not re.match('.*auto_null.*', i)]
        if not valid_elements:
            return None
        return valid_elements[0]

    def pactl_command(self, command, identifier, volume):
        if not command in ['set-sink-volume', 'set-source-volume']:
            return False
        if not volume in range(0, 100):
            return False
        if not isinstance(identifier, int):
            return False
        subprocess.check_call(['pactl',
                         command,
                         str(identifier),
                         str(volume) + '%'])
        return True


class Player(AudioObject):

    def __init__(self, frequency=DEFAULT_TEST_FREQUENCY, verbose=False):
        super(Player, self).__init__()
        self.verbose = verbose
        self.default_volume = 20 
        self.pipeline = gst.parse_launch('''audiotestsrc wave=sine freq=%s !
        audioconvert ! audioresample ! autoaudiosink''' % frequency)
        self.audio_type = 'sink'
        self.volumecontrol(self.default_volume)
        if self.verbose: 
            print("Playing test frequency of %s Hz" % frequency)

class Recorder(AudioObject):
    def __init__(self, loop=None, verbose=False):
        super(Recorder, self).__init__()
        self.verbose = verbose
        self.default_volume = 10
        self.raw_buffers = []
        self.fft_magnitudes = [0.0] * BINS
        self.fft_frequency_bands = [i * (SAMPLING_FREQUENCY / BINS / 2)
                for i in range(BINS)]
        self.fft_samples_taken = 0
        self.loop = loop

        self.pipeline = gst.parse_launch('''autoaudiosrc name=recordersrc
        ! queue
        ! level message=true name=recorderlevel
        ! audioconvert
        ! audio/x-raw-int,channels=1, rate=%(rate)s
        ! audioresample
        ! spectrum interval=%(fft_interval)s bands = %(bands)s
        ! wavenc
        ! appsink name=recordersink emit-signals=true''' %
        {'bands': BINS,
         'rate': SAMPLING_FREQUENCY,
         'fft_interval': FFT_INTERVAL})
        self.sink = self.pipeline.get_by_name('recordersink')
        self.sink.connect('new-buffer', self.nextbuffer)
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message', self.bus_message_handler)
        self.audio_type = 'source'
        self.volume = 0
        self.volumecontrol(self.volume)
        self.actions={'level':"Adjusting recording level",
                      'sample':"Recording audio samples"}
        self.print_update = True
        self.current_action= None
        self.previous_error = 0
        self.integral = 0
        self.error = 20


    def write_audio_to_file(self, file):
        try:
            with open(file, "wb") as f:
                f.write(''.join(self.raw_buffers))
                return True
        except (TypeError, IOError):
            return False

    def nextbuffer(self, sink):
        b = sink.emit('pull-buffer')
        self.raw_buffers.append(b.data)
        #each buffer starts at b.timestamp and has a length of
        #b.duration, in nanoseconds. Each sample then covers a time
        #period of b.duration / len(samples).

    def bus_message_handler(self, bus, message):
        if message.type == gst.MESSAGE_ELEMENT:
            if message.structure.get_name() == 'spectrum' and self.error<0.5:
                if self.current_action != 'sample':
                    self.current_action = 'sample'
                    self.print_update = True
                #We only need magnitude, phase is not needed
                #this is measured in dB (0 = maximum)
                self.fft_magnitudes = [((i*self.fft_samples_taken) + j) / 
                                       (self.fft_samples_taken + 1) 
                                       for i, j in zip(
                                       self.fft_magnitudes,
                                       message.structure['magnitude'])]
                self.fft_samples_taken += 1
                if self.fft_samples_taken >= 20:
                    self.loop.quit()

            if message.structure.get_name() == 'level':
                peak_value = message.structure['peak'][0]

                #This PID controller implementation does a nice job of
                #keeping recording levels close to the desired level.
                
                dt = 0.1 #Sample duration?
                Kp=1
                Ki=0.01
                Kd=0.02

                self.error = REC_LEVEL - peak_value
                self.integral = self.integral + (self.error * dt)
                derivative = (self.error - self.previous_error)/dt
                output = int((Kp * self.error) + (Ki * self.integral) + (Kd * derivative))
                self.previous_error = self.error
                #Restrict change rate to 5
                if output>5: output=5
                if output<-5: output=-5
                print("peak %s, target %s, error %s, change %s, vol %s" % 
                        (peak_value, REC_LEVEL, self.error, output, self.volume))
                self.volume+=output
                if self.volume > 80: self.volume = 80
                self.volumecontrol(self.volume)
        if self.verbose and self.print_update and self.current_action:
            print(self.actions[self.current_action])
            self.print_update = False


def main():
    gobject.threads_init()
    loop = gobject.MainLoop()

    try:
        if args.verbose: print("Creating sound player and recorder objects")
        p = Player(frequency=args.frequency, verbose=args.verbose)
        r = Recorder(loop=loop, verbose=args.verbose)
        gobject.timeout_add_seconds(0, lambda: p.start())
        gobject.timeout_add_seconds(0, lambda: r.start())
        gobject.timeout_add_seconds(args.test_duration, lambda: p.stop())
        gobject.timeout_add_seconds(args.test_duration, lambda: r.stop())
        gobject.timeout_add_seconds(args.test_duration, lambda: loop.quit())
        if args.verbose: print("playing/recording...")
        loop.run()
    except OSError:
        print("Error running a command", file=sys.stderr)
        return(2)
    except GError:
        print("Error processing gstreamer pipeline", file=sys.stderr)
        return(3)

    if args.audio:
        if args.verbose:
            print("Saving recorded audio as %s" % args.audio)
        if not r.write_audio_to_file(args.audio):
            print("Couldn't save recorded audio", file=sys.stderr)

    if args.spectrum:
        if args.verbose:
            print("Saving spectrum data for plotting as %s" % args.spectrum)
        try:
            with open(args.spectrum, "wb") as f:
                for i in range(len(r.fft_frequency_bands)):
                    print(r.fft_frequency_bands[i], r.fft_magnitudes[i], file=f)
        except (TypeError, IOError):
            print("Couldn't save spectrum data for plotting", file=sys.stderr)

    #Let's analyze the signal.

    for i in range(len(r.fft_frequency_bands)):
        if r.fft_frequency_bands[i] >= args.frequency:
            test_bin_index = i - 1
            break

    if not test_bin_index:
        print("Test frequency doesn't match any of the spectrum bins.",
                file=sys.stderr)
        return(4)

    average_magnitude = sum(r.fft_magnitudes) / len(r.fft_magnitudes)
    test_result = False
    microphone_broken = True

    for i in range(len(r.fft_magnitudes)):
        if r.fft_magnitudes[i] > average_magnitude:
            microphone_broken = False
        if r.fft_magnitudes[i] > average_magnitude + MAGNITUDE_THRESHOLD and \
           i == test_bin_index:
               if args.verbose:
                   print("Magnitude of %s in band %s is higher than "
                         "average (%s), test frequency of %s "
                         "contained in this band!" % 
                         (r.fft_magnitudes[i],
                          r.fft_frequency_bands[i],
                          average_magnitude,
                          args.frequency))
               test_result = True

    if args.verbose:
        subprocess.check_call(['pactl','list','sources'])

    if microphone_broken :
        print("Microphone seems broken, didn't even record ambient noise")

    if test_result and not microphone_broken:
        print("Test passed")
        return(0)
    else:
        print("Test failed")
        return(1)

if __name__ == "__main__":
    sys.exit(main())
