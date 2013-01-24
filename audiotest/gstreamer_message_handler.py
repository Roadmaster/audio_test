#!/usr/bin/env python

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

    def set_quit_method(self, method):
        """ Method that will be called when sampling is complete."""
        self._quit_method = method

    def bus_message_handler(self, bus, message):
        if message.type == gst.MESSAGE_ELEMENT:
            message_name = message.structure.get_name()
            if message_name == 'spectrum':
                fft_magnitudes = message.structure['magnitude']
                self.spectrum_method(self.spectrum_analyzer, fft_magnitudes)

            if message_name == 'level':
                #peak_value is our process feedback
                peak_value = message.structure['peak'][0]
                self.level_method(peak_value, self.pid_controller,
                                  self.volume_controller)

    #Adjust recording level
    def level_method(self, level, pid_controller, volume_controller):
        #If volume controller doesn't return a valid volume,
        #we can't control it :(
        current_volume = volume_controller.get_volume()
        if current_volume is None:
            self.logger.error("Unable to control recording volume."
                              "Test results may be wrong")
            return
        self.current_level = level
        change = pid_controller.input_change(level, 0.10)
        if self.logger:
            self.logger.debug("Peak level: %(peak_level).2f, "
                         "volume: %(volume)d%%, Volume change: %(change)f%%" %
                      {'peak_level': level,
                       'change': change,
                       'volume': current_volume})
        volume_controller.set_volume(current_volume + change)

    #Only sample if level is within the threshold
    def spectrum_method(self, analyzer, spectrum):
        if self.rec_level_range[1] <= self.current_level \
           or self.current_level <= self.rec_level_range[0]:
            self.logger.debug("Sampling, recorded %d samples" %
                               analyzer.number_of_samples)
            analyzer.sample(spectrum)
        if analyzer.sampling_complete() and self._quit_method:
            self.logger.info("Sampling complete, ending process")
            self._quit_method()
