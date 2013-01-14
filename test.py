#!/usr/bin/env python
from __future__ import print_function
from subprocess import CalledProcessError
import unittest
import audiotest 

class TestPIDController(unittest.TestCase):
    def test_pid(self):
        pid = audiotest.PIDController(Kp=0.3, Ki=0.5,Kd=0.7, setpoint=5)
        self.assertEqual(pid._integral, 0)

        process_feedback = 0
        input_change = pid.input_change(process_feedback, dt=0.1)
        self.assertEqual(input_change, 36.75)

    def test_pid_descending(self):
        pid = audiotest.PIDController(Kp=0.3, Ki=0.5,Kd=0.7, setpoint=5)
        self.assertEqual(pid._integral, 0)

        process_feedback = 50
        input_change = pid.input_change(process_feedback, dt=0.1)
        self.assertEqual(input_change, -330.75)


    def test_change_limiting_pid(self):
        """ Test that PID controller with change rate limiter doesn't
            send a change rate larger than the limit"""
        limit = 10
        pid = audiotest.PIDController(Kp=3, Ki=0.5,Kd=0.7, setpoint=50)
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
                            "module-alsa-card.c\ts16le 2ch 44100Hz\tSUSPENDED" + \
                            "\n" +\
"5\talsa_output.usb-0d8c_C-Media_USB_Headphone_Set-00-Set.analog-stereo\tmodule-alsa-card.c\ts16le 2ch 44100Hz\tSUSPENDED"

        self.pactl_input = "0\talsa_output.pci-0001_00_1b.0.analog-stereo.monitor\t" +\
                           "module-alsa-card.c\ts16le 2ch 44100Hz\tIDLE\n" +\
                           "1\talsa_input.pci-0001_00_1b.0.analog-stereo\t" +\
                           "module-alsa-card.c\ts16le 2ch 44100Hz\tSUSPENDED"  + \
                           "\n" + \
"10\talsa_output.usb-0d8c_C-Media_USB_Headphone_Set-00-Set.analog-stereo.monitor\tmodule-alsa-card.c\ts16le 2ch 44100Hz\tSUSPENDED" + \
                           "\n" + \
"11\talsa_input.usb-0d8c_C-Media_USB_Headphone_Set-00-Set.analog-mono\tmodule-alsa-card.c\ts16le 1ch 44100Hz\tRUNNING"

        self.pactl_null_output = "0\tauto_null\tmodule-null-sink.c\t" +\
                                 "s16le 2ch 44100Hz\tIDLE"
        self.pactl_null_input = "0\tauto_null.monitor\t" +\
                                "module-null-sink.c\ts16le 2ch 44100Hz\tIDLE"

    def test_invalid_type(self):
        vc = audiotest.PAVolumeController('invalid_type', method=lambda x: 
                                                   "doesnt matter")
        self.assertFalse(vc.get_identifier())
        self.assertFalse(vc.set_volume(10))
        self.assertFalse(vc.get_volume())

    def test_get_default_sink(self):
        vc = audiotest.PAVolumeController('output', method=lambda x: self.pactl_output)
        id = vc._get_identifier_for('output')
        self.assertEqual(id, (0, 'alsa_output.pci-0001_00_1b.0.analog-stereo'))

    def test_get_default_source(self):
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_input)
        id = vc._get_identifier_for('input')
        self.assertEqual(id, (1, 'alsa_input.pci-0001_00_1b.0.analog-stereo'))

    def test_get_sink_null(self):
        vc = audiotest.PAVolumeController('output', method=lambda x: self.pactl_null_output)
        id = vc._get_identifier_for('output')
        self.assertIsNone(id)

    def test_get_source_null(self):
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_null_input)
        id = vc._get_identifier_for('input')
        self.assertIsNone(id)

    def test_mute(self):
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertTrue(vc.mute(True))

    def test_set_invalid_volume(self):
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertFalse(vc.set_volume(101))
        self.assertFalse(vc.set_volume(-1))

    def test_set_valid_volume(self):
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertTrue(vc.set_volume(100))
        self.assertEqual(vc.get_volume(), 100)
        self.assertTrue(vc.set_volume(15))
        self.assertEqual(vc.get_volume(), 15)
        self.assertTrue(vc.set_volume(0))
        self.assertEqual(vc.get_volume(), 0)

    def test_set_volume_without_identifier(self):
        """ What happens if I don't explicitly call vc.get_identifier()"""
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_input)
        self.assertFalse(vc.set_volume(10))

    def test_get_volume(self):
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertTrue(vc.set_volume(15))
        self.assertEqual(15, vc.get_volume())

    def test_get_just_initialized_volume(self):
        """ By definition it's None until I explicitly set it to something """
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertEqual(None, vc.get_volume())

    def test_get_zero_volume(self):
        vc = audiotest.PAVolumeController('input', method=lambda x: self.pactl_input)
        vc.get_identifier()
        self.assertTrue(vc.set_volume(0))
        self.assertEqual(0, vc.get_volume())

    @unittest.skip("too slow")
    def test_command_executer(self):
        vc = audiotest.PAVolumeController('input', method=self.pactl_input)
        vc.get_identifier()
        print("Expect this to take 15 seconds")
        self.assertFalse(vc._pactl_output("false"))
        self.assertEqual('',vc._pactl_output("true"))

    def test_set_when_method_fails(self):
        vc = audiotest.PAVolumeController('input', method=self.pactl_input)
        vc.get_identifier()
        vc.method=lambda x: False 
        self.assertFalse(vc.set_volume(10))

    def test_method_return_false(self):
        vc = audiotest.PAVolumeController('input', method=lambda x: False)
        self.assertFalse(vc.get_identifier())


class TestSpectrumAnalyzer(unittest.TestCase):
    def setUp(self):
        self.test_spectrums=[[1, 2, 3, 4, 5], 
                        [6.0, 7.0, 8.0, 9.0, 10.0],
                        [16, 17, 18, 19, 20]]

        self.real_data = [-44.824, -42.680, -45.446, -52.929, -53.676, -53.883,
                -55.636, -56.875, -57.076, -57.882, -58.204, -58.352, -58.578,
                -58.347, -58.313, -58.660, -58.545, -58.660, -59.097, -58.899,
                -58.963, -58.823, -58.663, -58.469, -58.888, -59.281, -59.458,
                -59.394, -59.571, -59.749, -59.838, -59.928, -59.925, -59.943,
                -59.975, -59.948, -59.937, -59.909, -59.865, -59.857, -59.914,
                -59.978, -59.998, -59.998, -59.950, -59.948, -59.970, -59.959,
                -59.974, -59.987, -59.934, -59.920, -59.975, -59.985, -59.992,
                -59.991, -59.943, -59.986, -59.989, -59.979, -59.961, -59.993,
                -59.974, -59.993, -59.991, -59.963, -59.968, -59.967, -59.973,
                -59.981, -59.981, -59.992, -59.976, -59.984, -59.997, -59.957,
                -59.991, -59.996, -59.997, -59.971, -59.947, -59.995, -60.0,
                -59.846, -57.496, -59.000, -60.0, -60.0, -60.0, -60.0, -59.994,
                -59.991, -60.0, -60.0, -59.983, -59.960, -59.985, -59.993,
                -59.975, -59.978, -59.997, -60.0, -59.992, -59.960, -59.989,
                -60.0, -59.997, -59.969, -59.970, -59.994, -59.999, -59.970,
                -59.988, -60.0, -59.998, -59.980, -59.974, -59.989, -59.988,
                -59.983, -59.997, -59.989, -59.996, -59.997, -59.987, -59.996,
                -59.992, -60.0, -59.986, -59.991, -59.992, -59.995, -59.979,
                -59.975, -59.976, -60.0, -59.991, -60.0, -59.964, -59.984,
                -59.983, -59.985, -59.998, -59.994, -59.993, -60.0, -59.972,
                -59.995, -59.967, -59.966, -59.982, -59.976, -59.973, -59.991,
                -60.0, -60.0, -60.0, -59.990, -59.993, -59.979, -59.998,
                -59.948, -59.990, -59.987, -59.986, -59.997, -59.989, -59.991,
                -60.0, -59.999, -60.0, -59.998, -59.962, -60.0, -59.995,
                -59.994, -59.976, -59.975, -59.992, -59.995, -59.978, -60.0,
                -59.987, -59.994, -59.996, -59.982, -59.987, -59.986, -59.976,
                -59.997, -59.972, -59.957, -59.990, -59.980, -59.975, -60.0,
                -59.984, -59.999, -59.977, -59.998, -59.979, -59.986, -59.981,
                -59.993, -59.990, -59.995, -60.0, -59.997, -59.968, -59.965,
                -59.982, -59.977, -59.958, -59.981, -59.994, -59.982, -60.0,
                -59.964, -59.967, -60.0, -59.982, -59.985, -59.982, -59.989,
                -59.996, -59.995, -59.998, -59.994, -59.996, -59.984, -59.998,
                -59.981, -59.998, -60.0, -59.988, -60.0, -59.999, -60.0,
                -59.981, -59.986, -59.999, -60.0, -59.997, -59.996, -59.999,
                -60.0, -60.0, -60.0, -60.0, -60.0, -60.0, -59.997, -60.0,
                -60.0, -60.0, -59.992]


    def test_average_spectrum(self):
        sa = audiotest.SpectrumAnalyzer(points=5)
        for i in self.test_spectrums:
            sa.sample(i)
        self.assertEqual([(sum(e) / len(e)) for e in zip(*self.test_spectrums)], \
                     sa.spectrum)

    def test_different_sample_size(self):
        sa = audiotest.SpectrumAnalyzer(points=5)
        for i in self.test_spectrums:
            sa.sample(i)
        spectrum = sa.spectrum
        sa.sample(self.test_spectrums[0][1:])
        self.assertEqual(spectrum, sa.spectrum)

    def test_frequency_bands(self):
        sf = 19875
        p = 5
        sa = audiotest.SpectrumAnalyzer(points=p, sampling_frequency=sf)
        #Note *halving* because of sampling / real frequency relationship.
        expectedFrequencies = [(((sf/2.0) / p) * i) for i in range(p)]
        self.assertEqual(expectedFrequencies, sa.frequencies)

    def test_obtain_band_for(self):
        p = 5
        sf = 1500 #If sampling frequency is 1500 Hz, it means the
                  #maximum analyzable frequency is 750 Hz.
        sa = audiotest.SpectrumAnalyzer(points = p, sampling_frequency = sf)
        #These are *real* frequencies
        self.assertEqual(2, sa.frequency_band_for(450))
        self.assertIsInstance(sa.frequency_band_for(450), int)
        self.assertEqual(3, sa.frequency_band_for(451))
        self.assertEqual(None, sa.frequency_band_for(751))
        self.assertEqual(0, sa.frequency_band_for(1))

    def test_frequency_boundaries_for_band(self):
        p = 10
        sf = 3000
        #Maximum SF is 1500, so each bin will be *150 HZ*, not 300.
        sa = audiotest.SpectrumAnalyzer(points = p, sampling_frequency = sf)
        self.assertEqual((0, 150), sa.frequencies_for_band(0))
        self.assertEqual((1350, 1500), sa.frequencies_for_band(9))
        self.assertEqual(None, sa.frequencies_for_band(10))

    def test_real_signal(self):
        sa = audiotest.SpectrumAnalyzer(points=256)
        sa.sample(self.real_data)
        highest_bands = sa.frequencies_over_average(threshold=-2.0)
        print(highest_bands)
        #84 should be, 23 shouldn't
        self.assertIn(84, highest_bands)
        self.assertNotIn(23, highest_bands)

    def test_peaks(self):
        sa = audiotest.SpectrumAnalyzer(points=256)
        sa.sample(self.real_data)
        highest_bands = sa.twin_peaks(threshold=2.0)
        print(highest_bands)
        self.assertIn(84, highest_bands)
        self.assertNotIn(23, highest_bands)


#I really don't know how to test this :/
class TestGStreamerMessageHandler(unittest.TestCase):
    def setUp(self):
     gmh = audiotest.GStreamerMessageHandler(rec_level_range=None,
                                  logger=None,
                                  volumecontroller=None,
                                  pidcontroller=None,
                                  spectrum_analyzer=None)
       
    def test_handler(self):
        pass




if __name__ == '__main__':
    unittest.main()
