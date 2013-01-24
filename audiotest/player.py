#!/usr/bin/env python
class Player(GstAudioObject):
    def __init__(self, frequency=DEFAULT_TEST_FREQUENCY, logger=None):
        super(Player, self).__init__()
        self.pipeline_description = ("audiotestsrc wave=sine freq=%s "
                                "! audioconvert "
                                "! audioresample "
                                "! autoaudiosink" % int(frequency))
        self.logger = logger
        if self.logger:
            self.logger.debug(self.pipeline_description)
        self.pipeline = gst.parse_launch(self.pipeline_description)
