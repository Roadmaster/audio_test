#!/usr/bin/env python

class SpectrumAnalyzer(object):
    def __init__(self, points, sampling_frequency=44100,
                 wanted_samples=20):
        self.spectrum = [0] * points
        self.number_of_samples = 0
        self.wanted_samples = wanted_samples
        self.sampling_frequency = sampling_frequency
        #Frequencies should contain *real* frequency which is half of
        #the sampling frequency
        self.frequencies = [((sampling_frequency / 2.0) / points) * i
                            for i in range(points)]

    def _average(self):
        return sum(self.spectrum) / len(self.spectrum)

    def sample(self, sample):
        if len(sample) != len(self.spectrum):
            return
        self.spectrum = [((old * self.number_of_samples) + new) /
                         (self.number_of_samples + 1)
                         for old, new in zip(self.spectrum, sample)]
        self.number_of_samples += 1

    def frequencies_with_peak_magnitude(self, threshold=1.0):
        #First establish the base level
        per_magnitude_bins = collections.defaultdict(int)
        for magnitude in self.spectrum:
            per_magnitude_bins[magnitude] += 1
        base_level = max(per_magnitude_bins,
                         key=lambda x: per_magnitude_bins[x])
        #Now return all values that are higher (more positive)
        #than base_level + threshold
        peaks = []
        for i in range(1, len(self.spectrum) - 1):
            first_index = i - 1
            last_index = i + 1
            if self.spectrum[first_index] < self.spectrum[i] and \
                    self.spectrum[last_index] < self.spectrum[i] and \
                    self.spectrum[i] > base_level + threshold:
                peaks.append(i)

        return peaks

    def frequency_band_for(self, frequency):
        """Convenience function to tell me which band
           a frequency is contained in
        """
        #Note that actual frequencies are half of what the sampling
        #frequency would tell us. If SF is 44100 then maximum actual
        #frequency is 22050, and if I have 10 frequency bins each will
        #contain only 2205 Hz, not 4410 Hz.
        max_frequency = self.sampling_frequency / 2
        if frequency > max_frequency or frequency < 0:
            return None
        band = float(frequency) / (max_frequency / len(self.spectrum))
        return int(math.ceil(band)) - 1

    def frequencies_for_band(self, band):
        """Convenience function to tell me the delimiting frequencies
           for a band
        """
        if band >= len(self.spectrum) or band < 0:
            return None
        lower = self.frequencies[band]
        upper = lower + ((self.sampling_frequency / 2.0) / len(self.spectrum))
        return (lower, upper)

    def sampling_complete(self):
        return self.number_of_samples >= self.wanted_samples
