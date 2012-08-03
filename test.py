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
        self.assertEqual(vc.get(), 100)
        self.assertTrue(vc.set(15))
        self.assertEqual(vc.get(), 15)
        self.assertTrue(vc.set(0))
        self.assertEqual(vc.get(), 0)

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
        sa = pa.SpectrumAnalyzer(points=5)
        for i in self.test_spectrums:
            sa.sample(i)
        self.assertEqual([(sum(e) / len(e)) for e in zip(*self.test_spectrums)], \
                     sa.spectrum)

    def test_different_sample_size(self):
        sa = pa.SpectrumAnalyzer(points=5)
        for i in self.test_spectrums:
            sa.sample(i)
        spectrum = sa.spectrum
        sa.sample(self.test_spectrums[0][1:])
        self.assertEqual(spectrum, sa.spectrum)

    def test_frequency_bands(self):
        sf = 19875
        p = 5
        sa = pa.SpectrumAnalyzer(points=p, sampling_frequency=sf)
        #Note *halving* because of sampling / real frequency relationship.
        expectedFrequencies = [(((sf/2.0) / p) * i) for i in range(p)]
        self.assertEqual(expectedFrequencies, sa.frequencies)

    def test_higher_than_average_bands(self):
        sa = pa.SpectrumAnalyzer(points=5)
        threshold = 5
        for i in self.test_spectrums:
            sa.sample(i)
        #Feed an artificially inflated reading.
        sa.sample([10,500,10,500,20])
        #Get indexes from bands whose magnitude surpasses the average by
        #the given threshold
        highest_bands = sa.frequencies_over_average(threshold=threshold)
        self.assertEqual([1,3], highest_bands)

    def test_obtain_band_for(self):
        p = 5
        sf = 1500 #If sampling frequency is 1500 Hz, it means the
                  #maximum analyzable frequency is 750 Hz.
        sa = pa.SpectrumAnalyzer(points = p, sampling_frequency = sf)
        #These are *real* frequencies
        self.assertEqual(2, sa.frequency_band_for(450))
        self.assertIsInstance(sa.frequency_band_for(450), int)
        self.assertEqual(3, sa.frequency_band_for(451))
        self.assertEqual(None, sa.frequency_band_for(751))
        self.assertEqual(0, sa.frequency_band_for(1))

    def test_frequency_boundaries_for_band(self):
        p = 10
        sf = 3000
        #Maximum SF is 300, so each bin will be *150 HZ*, not 300.
        sa = pa.SpectrumAnalyzer(points = p, sampling_frequency = sf)
        self.assertEqual((0, 150), sa.frequencies_for_band(0))
        self.assertEqual((1350, 1500), sa.frequencies_for_band(9))
        self.assertEqual(None, sa.frequencies_for_band(10))


#I really don't know how to test this :/
class TestGStreamerMessageHandler(unittest.TestCase):
    def setUp(self):
        methods={'level': lambda x: x, 'spectrum': lambda x: x}
        gmh = pa.GStreamerMessageHandler(methods)
        
    def test_handler(self):
        pass




if __name__ == '__main__':
    unittest.main()
