#!/usr/bin/env python3

import logging
import sys
import re
import json

from gi.repository import GObject
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst
Gst.init(None)  # This has to be done very early so it can find elements

#Frequency bands for FFT
BINS = 256
#How often to take a sample and do FFT on it.
FFT_INTERVAL = 100000000  # In nanoseconds, so this is every 1/10th second
#Sampling frequency. The effective maximum frequency we can analyze is
#half of this (see Nyquist's theorem)
SAMPLING_FREQUENCY = 44100
raw_buffers=[]
globo=5

def parse_spectrum_structure(text):
    #First let's jsonize this
    #This is the message name, which we don't need
    text = text.replace("spectrum, ", "")
    #name/value separator in json is : and not =
    text = text.replace("=",": ")
    #Mutate the {} array notation from the structure to
    #[] notation for json.
    text = text.replace("{","[")
    text = text.replace("}","]")
    #Remove a few stray semicolons that aren't needed
    text = text.replace(";","")
    #Remove the data type fields, as json doesn't need them
    text = re.sub(r"\(.+?\)", "", text)
    #double-quote the identifiers
    text = re.sub(r"([\w-]+):", r'"\1":', text)
    #Wrap the whole thing in brackets
    text = ("{"+text+"}")
    #Try to parse and return something sensible here, even if
    #the data was unparsable.
    try:
        return json.loads(text)
    except ValueError:
        return None


#This method gets called when we have a new buffer to handle
def buffer_handler(sink):
    print("Handling a buffer %s" % sink)
    sample = sink.emit('pull-sample')
    return True
    # FIXME: PyGI makes it impossible to get the buffer
    # data in a direct way.
    # https://bugzilla.gnome.org/show_bug.cgi?id=678663
    (success, data) = sample.get_buffer().map_range(0, -1,
                                        Gst.MapFlags.READ)
    print(success,data)
    if False and success:
        #Data should be in the address pointed to by data.memory
        #size is data.size
        from ctypes import string_at

        hex_data = string_at(id(data.memory), data.size)

        raw_buffers.append(hex_data)
    else:
        #FIXME: This needs to go.
        print("FAIL")
    return True

#This method gets called when  there's a message in the bus
def bus_message_handler(bus, message):
    print("Handling a message")
    if message.type == Gst.MessageType.ELEMENT:
        message_name = message.get_structure().get_name()
        print(message_name)
        if message_name == 'spectrum':
            #FIXME: Need to figure out the correct element in the structure
            #that contains the magnitudes
            #https://bugzilla.gnome.org/show_bug.cgi?id=693168
            structure = message.get_structure()
            print(structure.to_string())
            return
            print(parse_spectrum_structure(structure.to_string())['magnitude'])
            #Do something with fft_magnitudes here


        if message_name == 'level':
            #peak_value is our process feedback
            #It's returned as an array, so I need the first (and only)
            #element
            peak_value = message.get_structure().get_value('peak')[0]
            #No further need to debug, peak value works fine
#            print("peak is %s" % peak_value)
            #Do something with peak_value here



class GstAudioObject(object):
    def __init__(self):
        self.class_name = self.__class__.__name__

    def _set_state(self, state, description):
        self.pipeline.set_state(state)
        message = "%s: %s" % (self.class_name, description)
        if self.logger:
            self.logger.info(message)

    def start(self):
        self._set_state(Gst.State.PLAYING, "Starting")

    def stop(self):
        self._set_state(Gst.State.NULL, "Stopping")


class Recorder(GstAudioObject):
    def __init__(self, bins=BINS, sampling_frequency=SAMPLING_FREQUENCY,
                 fft_interval=FFT_INTERVAL, logger=None):
        super(Recorder, self).__init__()
        pipeline_description = ('''autoaudiosrc
        ! queue
        ! level message=true
        ! audioconvert
        ! audio/x-raw, channels=1, rate=(int)%(rate)s
        ! audioresample
        ! spectrum interval=%(fft_interval)s bands = %(bands)s
        ! wavenc
        ! appsink name=recordersink emit-signals=true''' %
        {'bands': bins,
         'rate': sampling_frequency,
         'fft_interval': fft_interval})
        self.logger = logger
        if self.logger:
            self.logger.debug(pipeline_description)
        self.pipeline = Gst.parse_launch(pipeline_description)

    def register_message_handler(self, handler_method):
        if self.logger:
            message = "Registering message handler: %s" % handler_method
            self.logger.debug(message)
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message', handler_method)

    def register_buffer_handler(self, handler_method):
        if self.logger:
            message = "Registering buffer handler: %s" % handler_method
            self.logger.debug(message)
        self.sink = self.pipeline.get_by_name('recordersink')
        self.sink.connect('new-sample', handler_method)


def main():
   #Setup logging
    level = logging.DEBUG
    logging.basicConfig(level=level)
    try:
        #Launches recording pipeline. I need to hook up into the Gst
        #messages.
        recorder = Recorder(logger=logging)
    except GObject.GError as excp:
        logging.critical("Unable to initialize GStreamer pipelines: %s", excp)
        sys.exit(127)

    #I need to tell the recorder which method will handle messages.
    recorder.register_message_handler(bus_message_handler)
    #recorder.register_buffer_handler(buffer_handler)

    #Create the loop and add a few triggers
    GObject.threads_init()
    loop = GObject.MainLoop()
    GObject.timeout_add_seconds(0, recorder.start)
    GObject.timeout_add_seconds(5, loop.quit)

    loop.run()

    #When the loop ends, set things back to reasonable states
    recorder.stop()

if __name__ == "__main__":
    sys.exit(main())
