#!/usr/bin/env python

from __future__ import division, print_function
#from gi.repository import Gst, GObject
import argparse
import gobject
import gst
import math
import struct
import subprocess
import sys

BINS = 256
SAMPLING_FREQUENCY = 44100
REC_LEVEL_RANGE = (-2.0, -3.5)


def dft(x, inverse = False, verbose = False) :
    N = len(x)
    inv = -1 if not inverse else 1
    X =[0] * N
    for k in range(N) :
        for n in range(N) :
            X[k] += x[n] * math.e**(inv * 2j * math.pi * k * n / N)
        if inverse :
            X[k] /= N
    return X


def fft_CT(x, inverse = False, verbose = False) :
    N = len(x)
    inv = -1 if not inverse else 1
    if N % 2 :
        return dft(x, inverse, False)
    x_e = x[::2]
    x_o  = x[1::2]
    X_e = fft_CT(x_e, inverse, False)
    X_o  = fft_CT(x_o, inverse, False)
    X = []
    M = N // 2
    for k in range(M) :
        X += [X_e[k] + X_o[k] * math.e ** (inv * 2j * math.pi * k / N)]
    for k in range(M,N) :
        X += [X_e[k-M] - X_o[k-M] * math.e ** (inv * 2j * math.pi * (k-M) / N)]
    if inverse :
        X = [j/2 for j in X]
    return X


class AudioObject:
    def start(self):
        self.pipeline.set_state(gst.STATE_PLAYING)

    def stop(self):
        self.pipeline.set_state(gst.STATE_NULL)


class Player(AudioObject):
    def __init__(self, frequency=8000):
        self.pipeline = gst.parse_launch('''audiotestsrc wave=sine freq=%s !
        audioconvert ! audioresample ! autoaudiosink name=sunk''' % frequency)


class Recorder(AudioObject):
    def __init__(self):
        self.raw_buffers = []
        self.fft_magnitudes = [0.0] * BINS
        self.fft_frequencies = [i * (SAMPLING_FREQUENCY / BINS / 2) for i in range(BINS)]

        self.pipeline = gst.parse_launch('''autoaudiosrc name=recordersrc
        ! queue
        ! level message=true name=recorderlevel
        ! audioconvert
        ! audio/x-raw-int,channels=1, rate=44100
        ! audioresample
        ! spectrum interval=100000000 bands = %(bands)s
        ! wavenc
        ! appsink name=recordersink emit-signals=true''' %
        {'bands': BINS})
        self.sink = self.pipeline.get_by_name('recordersink')
        self.sink.connect('new-buffer', self.nextbuffer)
        self.recordersource = self.pipeline.get_by_name('recordersrc')
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message',self.leveler)
        self.volume = 0
        self.volumecontrol(self.volume)

    @property
    def samples(self):
        stream=''.join(self.raw_buffers)
        values = struct.unpack("h" *(len(stream)//2),''.join(stream))
        return values

    def write_audio_to_file(self, file):
        try:
            with open(file,"wb") as f:
                f.write(''.join(self.raw_buffers))
                return True
        except (TypeError, IOError):
            return False

    def write_wave_to_file(self, file):
        ''' Writes all the samples, one per line, to a file
        for plotting or other analysis.'''
        try:
            with open(file,"wb") as f:
                for sample in self.samples:
                    print(sample, file=f)
                return True
        except (TypeError, IOError):
            return False

    def nextbuffer(self, sink):
        b= sink.emit('pull-buffer')
        self.raw_buffers.append(b.data)
        #each buffer starts at b.timestamp and has a length of
        #b.duration, in nanoseconds. Each sample then covers a time
        #period of b.duration / len(samples).

    def leveler(self, bus, message):
        if message.type == gst.MESSAGE_ELEMENT:
            if message.structure.get_name() == 'spectrum' and self.in_range:
                #We only need magnitude, phase is not needed
                #this is measured in dB (0 = maximum)
                #We need to divide the sampling frequency by number of
                #bins just as with the manual FFT
                #Add magnitudes!
                self.fft_magnitudes=[i + j for i,j in zip(self.fft_magnitudes, message.structure['magnitude'])]

            if message.structure.get_name() == 'level' :
                peak_value = message.structure['peak'][0]
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

    def volumecontrol(self,volume):
        subprocess.call(['pactl',
                         'set-source-volume',
                          '1',
                          str(volume)+'%'])



class SpectrumAnalyzer:
    def __init__(self):
        self.fft = [0]*BINS
        #Calculate the starting frequency for each bin
        #NOTE we go only up to BINS//2 because of the sampling
        #theorem and the fourier transform's symmetricality
        #for purely real data
        self.frequencies = [(SAMPLING_FREQUENCY / BINS) * i
                            for i in range(BINS//2)]

    def dft(self, data):
        pass


    def fft_chunk(self, chunk):
        ''' Takes a chunk of BINS size, converts to
        frequency domain with FFT and adds to total FFT'''
        #TODO: sanitize chunk size, must be exactly BINS
        chunk_fft = fft_CT(chunk, verbose=False)
        self.fft=[self.fft[i] + chunk_fft[i] for i in range(BINS)]

    def fft_samples(self, samples):
        '''Calculates frequency components for the signal
        given in samples. Assumes dividing SAMPLING_FREQUENCY into
        BINS bands.'''

        #Make number of samples a multiple of BINS by truncating the remainder
        data = samples[0:len(samples) - (len(samples) % BINS)]

        #Iterate in BINS-sized chunks and calculate fft for each one
        for i in range(0,len(data),BINS):
            chunk = data[i:i + BINS]
            self.fft_chunk(chunk)

    @property
    def spectrum(self):
        ''' Spectrum data after doing FFT calculations.
            Returns a list with BINS tuples, first element
            of each tuple is the bin's starting frequency
            and second is the magnitude for frequencies
            in that bin. '''
        return [(self.frequencies[i], abs(self.fft[i]))
                for i in range(len(self.fft)//2)]

    def write_fft_to_file(self, file):
        ''' Writes frequency bins and their magnitude, one per line,
        to a file for plotting or other analysis.'''
        try:
            with open(file,"wb") as f:
                for i in range(len(s.fft)//2):
                    print(self.frequencies[i], abs(self.fft[i]), file=f)
                return True
        except (TypeError, IOError):
            return False


parser = argparse.ArgumentParser()
parser.add_argument("-t", "--time",
        dest='test_duration',
        action='store',
        default=2,
        type=int,
        help="Test duration, default %(default)s seconds")
parser.add_argument("-a","--audio",
        action='store',
        default=None,
        type=str,
        help="File to save recorded audio")
parser.add_argument("-f","--frequency",
        action='store',
        default=8000,
        type=int,
        help="Frequency for test signal, default (%default)s Hz")
parser.add_argument("-u","--spectrum",
        action='store',
        type=str,
        help="File to save spectrum information for plotting")
parser.add_argument("-w","--wave",
        action='store',
        type=str,
        help="File to save waveform data for plotting")
args = parser.parse_args()

gobject.threads_init()
loop = gobject.MainLoop()

p = Player(frequency=args.frequency)
r = Recorder()
gobject.timeout_add_seconds(0, lambda : p.start())
gobject.timeout_add_seconds(0, lambda : r.start())
gobject.timeout_add_seconds(args.test_duration, lambda : p.stop())
gobject.timeout_add_seconds(args.test_duration, lambda : r.stop())
gobject.timeout_add_seconds(args.test_duration, lambda : loop.quit())
loop.run()

for i in range(len(r.fft_magnitudes)):
    print(r.fft_frequencies[i],r.fft_magnitudes[i])
sys.exit()
s = SpectrumAnalyzer()
s.fft_samples(r.samples)


if args.audio:
    if not r.write_audio_to_file(args.audio):
        sys.stderr.write("Couldn't save recorded audio")

if args.wave:
    if not r.write_wave_to_file(args.wave):
        sys.stderr.write("Couldn't save wave data for plotting")

if args.spectrum:
    if not s.write_fft_to_file(args.spectrum):
        sys.stderr.write("Couldn't save spectrum data for plotting")


#Can feed a known signal here to test fft behavior (100-Hz sinusoidal wave)
#data=[65535 * (math.sin(2*math.pi*x/(SAMPLING_FREQUENCY/1000)))
#        for x in range(5*SAMPLING_FREQUENCY-(5*SAMPLING_FREQUENCY)%BINS)]

#We want to know if the bin with the highest magnitude (second element)
#contains the test frequency.

for i in range(len(s.spectrum)):
    if s.spectrum[i][0] >= args.frequency:
        test_bin=s.spectrum[i-1]
        break

if not test_bin:
   print("Test frequency doesn't match any of the spectrum bins.")
   sys.exit(127)

#Ignore the first bin(dc component mostly)
max_bin=(max(s.spectrum[1:], key=lambda x: x[1]))
print("Frequency bin with the highest magnitude is %s-%s" %
        (max_bin[0], s.spectrum[s.spectrum.index(max_bin)+1][0]))
print("Frequency bin containing the test frequency of %d Hz is %s-%s" %
        (args.frequency,test_bin[0], s.spectrum[s.spectrum.index(test_bin)+1][0] ))
if max_bin == test_bin:
    print("Success!")
    sys.exit(0)
else:
    print("Failure :(")
    sys.exit(1)

