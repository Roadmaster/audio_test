#!/usr/bin/env python3
from gi.repository import Gst
Gst.init(None)
#This is just to test gst parsing and launching on python3.
pipe = Gst.parse_launch("autoaudiosrc ! "
                        "audioconvert ! "
                        "audio/x-raw-int,channels=1,rate=(int)44100 ! audioresample ! wavenc ! filesink location=/tmp/a.wav")
