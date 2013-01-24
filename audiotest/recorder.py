#!/usr/bin/env python

from audiotest.gst_audio_object import GstAudioObject

class Recorder(GstAudioObject):
    def __init__(self, bins=BINS, sampling_frequency=SAMPLING_FREQUENCY,
                 fft_interval=FFT_INTERVAL, logger=None):
        super(Recorder, self).__init__()
        pipeline_description = ('''autoaudiosrc
        ! queue
        ! level message=true
        ! audioconvert
        ! audio/x-raw-int, channels=1, rate=%(rate)s
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
        self.pipeline = gst.parse_launch(pipeline_description)

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
        self.sink.connect('new-buffer', handler_method)
