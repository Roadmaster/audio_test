#!/usr/bin/env python

class GStreamerRawAudioRecorder(object):
    def __init__(self):
        self.raw_buffers = []

    def buffer_handler(self, sink):
        buffer = sink.emit('pull-buffer')
        self.raw_buffers.append(buffer.data)

    def get_raw_audio(self):
        return ''.join(self.raw_buffers)
