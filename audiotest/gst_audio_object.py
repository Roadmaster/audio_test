#!/usr/bin/env python

class GstAudioObject(object):
    def __init__(self):
        self.class_name = self.__class__.__name__

    def _set_state(self, state, description):
        self.pipeline.set_state(state)
        message = "%s: %s" % (self.class_name, description)
        if self.logger:
            self.logger.info(message)

    def start(self):
        self._set_state(gst.STATE_PLAYING, "Starting")

    def stop(self):
        self._set_state(gst.STATE_NULL, "Stopping")
