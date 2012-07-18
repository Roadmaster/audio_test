#!/usr/bin/env python3

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


import argparse

BINS = 256
SAMPLING_FREQUENCY = 44100
REC_LEVEL_RANGE = (-2.0, -3.5)

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
parser = argparse.ArgumentParser()
parser.add_argument("-t", "--time",
        dest='test_duration',
        action='store',
        default=30,
        type=int,
        help="""Maximum test duration, default %(default)s seconds.  """)
parser.add_argument("-a", "--audio",
        action='store',
        default=None,
        type=str,
        help="File to save recorded audio")
parser.add_argument("-f", "--frequency",
        action='store',
        default=DEFAULT_TEST_FREQUENCY,
        type=int,
        help="Frequency for test signal, default %(default)s Hz")
parser.add_argument("-u", "--spectrum",
        action='store',
        type=str,
        help="File to save spectrum information for plotting")
args = parser.parse_args()

#import rest of the modules; specifically, Gst, because otherwise
#it interferes with argument processing.
from gi.repository import GObject, Gst, GLib
import subprocess
import sys


class AudioObject:
    def start(self):
        self.pipeline.set_state(Gst.State.PLAYING)

    def stop(self):
        self.pipeline.set_state(Gst.State.NULL)
        self.volumecontrol(self.default_volume)

    def pactl_command(self, command, identifier, volume):
        if not command in ['set-sink-volume', 'set-source-volume']:
            return
        if not volume in range(0, 100):
            return
        if not isinstance(identifier, int):
            return
        subprocess.check_call(['pactl',
                         command,
                         str(identifier),
                         str(volume) + '%'])


class Player(AudioObject):

    def __init__(self, frequency=8000):
        self.default_volume = 70
        self.pipeline = Gst.parse_launch('''audiotestsrc wave=sine freq=%s !
        audioconvert ! audioresample ! autoaudiosink''' % frequency)
        self.volumecontrol(self.default_volume)

    def volumecontrol(self, volume):
        self.pactl_command('set-sink-volume', 0, volume)


class Recorder(AudioObject):
    def __init__(self, loop=None):
        self.default_volume = 10
        self.raw_buffers = []
        self.fft_magnitudes = [0.0] * BINS
        self.fft_frequency_bands = [i * (SAMPLING_FREQUENCY / BINS / 2)
                for i in range(BINS)]
        self.fft_samples_taken = 0
        self.loop = loop
        self.in_range = False

        self.pipeline = Gst.parse_launch('''autoaudiosrc name=recordersrc
        ! queue
        ! level message=true name=recorderlevel
        ! audioconvert
        ! audio/x-raw,channels=1, rate=(int)44100
        ! audioresample
        ! spectrum interval=100000000 bands = %(bands)s
        ! wavenc
        ! appsink name=recordersink emit-signals=true''' %
        {'bands': BINS})
        self.sink = self.pipeline.get_by_name('recordersink')
        self.sink.connect('new-sample', self.nextbuffer)
        self.recordersource = self.pipeline.get_by_name('recordersrc')
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message', self.bus_message_handler)
        self.volume = 0
        self.volumecontrol(self.volume)

    def write_audio_to_file(self, file):
        try:
            with open(file, "wb") as f:
                f.write(''.join(self.raw_buffers))
                return True
        except (TypeError, IOError):
            return False

    def nextbuffer(self, sink):
        b = sink.emit('pull-sample')
	#FIXME: THis is not working with pygi, I don't know
	#how to get the buffer's data to append to self.raw_buffers :(
        print(b.get_buffer())
        self.raw_buffers.append(b.get_buffer())
        #each buffer starts at b.timestamp and has a length of
        #b.duration, in nanoseconds. Each sample then covers a time
        #period of b.duration / len(samples).

    def bus_message_handler(self, bus, message):
        if message and message.type == Gst.MessageType.ELEMENT:
            if message.get_structure().get_name() == 'spectrum' and self.in_range:
                #We only need magnitude, phase is not needed
                #this is measured in dB (0 = maximum)
                #We need to divide the sampling frequency by number of
                #bins just as with the manual FFT
                self.fft_magnitudes = [i + j for i, j in zip(
                                       self.fft_magnitudes,
                                       message.get_structure()['magnitude'])]
                self.fft_samples_taken += 1
                if self.fft_samples_taken >= 20:
                    self.loop.quit()

            if message.get_structure().get_name() == 'level':
                peak_value = message.get_structure().get_fraction('peak')[0]
                # A simple hysteresis mechanism to keep peak signal levels
                # in a reasonable range, so that we neither clip nor
                # have a too-low signal.
                if REC_LEVEL_RANGE[1] <= peak_value <= REC_LEVEL_RANGE[0]:
                        self.in_range = True
                else:
                        self.in_range = False
                if not self.in_range:
                    if peak_value > REC_LEVEL_RANGE[0]:
                        self.volume -= 1
                    if peak_value < REC_LEVEL_RANGE[1]:
                        self.volume += 1
                    #print("adjusting volume to %d" % self.volume)
                    self.volumecontrol(self.volume)

    def volumecontrol(self, volume):
        self.pactl_command('set-source-volume', 1, volume)
        


GObject.threads_init()
Gst.init(None)
loop = GObject.MainLoop()

try:
    p = Player(frequency=args.frequency)
    r = Recorder(loop=loop)
    GObject.timeout_add_seconds(0, lambda: p.start())
    GObject.timeout_add_seconds(0, lambda: r.start())
    GObject.timeout_add_seconds(args.test_duration, lambda: p.stop())
    GObject.timeout_add_seconds(args.test_duration, lambda: r.stop())
    GObject.timeout_add_seconds(args.test_duration, lambda: loop.quit())
    loop.run()
except OSError:
    print("Error running a command", file=sys.stderr)
    sys.exit(2)
except GLib.GError:
    print("Error processing Gstreamer pipeline", file=sys.stderr)
    sys.exit(3)


if args.audio:
    if not r.write_audio_to_file(args.audio):
        sys.stderr.write("Couldn't save recorded audio")

if args.spectrum:
    try:
        with open(args.spectrum, "wb") as f:
            for i in range(len(r.fft_frequency_bands)):
                print(r.fft_frequency_bands[i], r.fft_magnitudes[i], file=f)
    except (TypeError, IOError):
        sys.stderr.write("Couldn't save spectrum data for plotting")

#We want to know if the bin with the highest magnitude (second element)
#contains the test frequency.

for i in range(len(r.fft_frequency_bands)):
    if r.fft_frequency_bands[i] >= args.frequency:
        test_bin_index = i - 1
        break

if not test_bin_index:
    print("Test frequency doesn't match any of the spectrum bins.")
    sys.exit(127)

#TODO:We should ignore the first band (which will contain mostly the DC
#component and low-frequency noise) *only* if it doesn't contain the test
#frequency.
max_bin = max(r.fft_magnitudes[1:])
max_bin_index = r.fft_magnitudes.index(max_bin)
print("Frequency bin with the highest magnitude is %s-%s" %
         (r.fft_frequency_bands[max_bin_index],
          r.fft_frequency_bands[max_bin_index + 1]))
print("Frequency bin containing the test frequency of %d Hz is %s-%s" %
        (args.frequency, r.fft_frequency_bands[test_bin_index],
         r.fft_frequency_bands[test_bin_index + 1]))
if max_bin_index == test_bin_index:
    print("Success!")
    sys.exit(0)
else:
    print("Failure :(")
    sys.exit(1)
