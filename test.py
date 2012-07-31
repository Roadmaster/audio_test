#!/usr/bin/env python
from __future__ import print_function
from subprocess import CalledProcessError
import unittest
import panew as pa

class TestPIDController(unittest.TestCase):
    def test_pid(self):
        pid = pa.PIDController(Kp=0.3, Ki=0.5,Kd=0.7, setpoint=5)
        self.assertEqual(pid.integral, 0)

        process_feedback = 0
        input_change = pid.input_change(process_feedback, dt=0.1)
        self.assertEqual(input_change, 36.75)

    def test_pid_descending(self):
        pid = pa.PIDController(Kp=0.3, Ki=0.5,Kd=0.7, setpoint=5)
        self.assertEqual(pid.integral, 0)

        process_feedback = 50
        input_change = pid.input_change(process_feedback, dt=0.1)
        self.assertEqual(input_change, -330.75)


    def test_change_limiting_pid(self):
        """ Test that PID controller with change rate limiter doesn't
            send a change rate larger than the limit"""
        limit = 10
        pid = pa.PIDController(Kp=3, Ki=0.5,Kd=0.7, setpoint=50)
        pid.set_change_limit(limit)

        process_feedback = 0
        input_change = pid.input_change(process_feedback, dt=0.1)
        self.assertTrue(input_change <= limit)

        #This should decrease the input
        process_feedback = 1500
        input_change = pid.input_change(process_feedback, dt=0.1)
        self.assertTrue(abs(input_change) <= limit)
        self.assertTrue(input_change / abs(input_change) == -1)

class TestVolumeControl(unittest.TestCase):

    def setUp(self):
        self.pactl_output = "0\talsa_output.pci-0001_00_1b.0.analog-stereo\t" + \
                            "module-alsa-card.c\ts16le 2ch 44100Hz\tSUSPENDED"

        self.pactl_input = "0\talsa_output.pci-0001_00_1b.0.analog-stereo.monitor\t" +\
                           "module-alsa-card.c\ts16le 2ch 44100Hz\tIDLE\n" +\
                           "1\talsa_input.pci-0001_00_1b.0.analog-stereo\t" +\
                           "module-alsa-card.c\ts16le 2ch 44100Hz\tSUSPENDED"

        self.pactl_null_output = "0\tauto_null\tmodule-null-sink.c\t" +\
                                 "s16le 2ch 44100Hz\tIDLE"
        self.pactl_null_input = "0\tauto_null.monitor\t" +\
                                "module-null-sink.c\ts16le 2ch 44100Hz\tIDLE"

    def test_invalid_type(self):
        vc = pa.PAVolumeController('invalid_type', method=lambda x: 
                                                   "doesnt matter")
        self.assertFalse(vc.get_identifier())
        self.assertFalse(vc.set(10))
        self.assertFalse(vc.get())

    def test_get_default_sink(self):
        vc = pa.PAVolumeController('output', method=lambda x: self.pactl_output)
        id = vc._get_identifier_for('output')
        self.assertEqual(id, (0, 'alsa_output.pci-0001_00_1b.0.analog-stereo'))

    def test_get_default_source(self):
        vc = pa.PAVolumeController('input', method=lambda x: self.pactl_input)
        id = vc._get_identifier_for('input')
        self.assertEqual(id, (1, 'alsa_input.pci-0001_00_1b.0.analog-stereo'))

    def test_get_sink_null(self):
        vc = pa.PAVolumeController('output', method=lambda x: self.pactl_null_output)
        id = vc._get_identifier_for('output')
        self.assertIsNone(id)

    def test_get_source_null(self):
        vc = pa.PAVolumeController('input', method=lambda x: self.pactl_null_input)
        id = vc._get_identifier_for('input')
        self.assertIsNone(id)

    def test_set_invalid_volume(self):
        vc = pa.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertFalse(vc.set(101))
        self.assertFalse(vc.set(-1))

    def test_set_valid_volume(self):
        vc = pa.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertTrue(vc.set(100))
        self.assertTrue(vc.set(15))
        self.assertTrue(vc.set(0))

    def test_set_volume_without_identifier(self):
        """ What happens if I don't explicitly call vc.get_identifier()"""
        vc = pa.PAVolumeController('input', method=lambda x: self.pactl_input)
        self.assertFalse(vc.set(10))

    def test_get_volume(self):
        vc = pa.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertTrue(vc.set(15))
        self.assertEqual(15, vc.get())

    def test_get_just_initialized_volume(self):
        """ By definition it's None until I explicitly set it to something """
        vc = pa.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertEqual(None, vc.get())

    def test_get_zero_volume(self):
        vc = pa.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertTrue(vc.set(0))
        self.assertEqual(0, vc.get())

    def test_command_executer(self):
        vc = pa.PAVolumeController('input', method=self.pactl_input)
        vc.get_identifier()
        self.assertFalse(vc._pactl_output("false"))

    def test_set_when_method_fails(self):
        vc = pa.PAVolumeController('input', method=self.pactl_input)
        vc.get_identifier()
        vc.method=lambda x: False 
        self.assertFalse(vc.set(10))


class TestSpectrumAnalyzer(unittest.TestCase):
    def setUp(self):
        self.test_spectrums=[[1, 2, 3, 4, 5], 
                        [6.0, 7.0, 8.0, 9.0, 10.0],
                        [16, 17, 18, 19, 20]]

    def test_average_spectrum(self):
        sa = pa.SpectrumAnalyzer()
        for i in self.test_spectrums:
            sa.sample(i)
        self.assertEqual([(sum(e) / len(e)) for e in zip(*self.test_spectrums)], \
                     sa.spectrum)
        

if __name__ == '__main__':
    unittest.main()
