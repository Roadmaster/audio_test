#!/usr/bin/env python

class PAVolumeController(object):
    pa_types = {'input': 'source', 'output': 'sink'}

    def __init__(self, type, method=None, logger=None):
        """Initializes the volume controller.

           Arguments:
           type: either input or output
           method: a method that will run a command and return pulseaudio
           information in the described format, as a single string with
           line breaks (to be processed with str.splitlines())

        """
        self.type = type
        self._volume = None
        self.identifier = None
        self.method = method
        if not isinstance(method, collections.Callable):
            self.method = self._pactl_output
        self.logger = logger

    def set_volume(self, volume):
        if not 0 <= volume <= 100:
            return False
        if not self.identifier:
            return False
        command = ['pactl',
                   'set-%s-volume' % (self.pa_types[self.type]),
                   str(self.identifier[0]),
                   str(int(volume)) + "%"]
        if False == self.method(command):
            return False
        self._volume = volume
        return True

    def get_volume(self):
        if not self.identifier:
            return None
        return self._volume

    def mute(self, mute):
        mute = str(int(mute))
        if not self.identifier:
            return False
        command = ['pactl',
                   'set-%s-mute' % (self.pa_types[self.type]),
                   str(self.identifier[0]),
                   mute]
        if False == self.method(command):
            return False
        return True

    def get_identifier(self):
        if self.type:
            self.identifier = self._get_identifier_for(self.type)
            if self.identifier and self.logger:
                message = "Using PulseAudio identifier %s (%s) for %s" %\
                       (self.identifier + (self.type,))
                self.logger.info(message)
            return self.identifier

    def _get_identifier_for(self, type):
        """Gets default PulseAudio identifier for given type.

           Arguments:
           type: either input or output

           Returns:
           A tuple: (pa_id, pa_description)

        """

        if type not in self.pa_types:
            return None
        command = ['pactl', 'list', self.pa_types[type] + "s", 'short']

        #Expect lines of this form (field separator is tab):
        #<ID>\t<NAME>\t<MODULE>\t<SAMPLE_SPEC_WITH_SPACES>\t<STATE>
        #What we need to return is the ID for the first element on this list
        #that does not contain auto_null or monitor.
        pa_info = self.method(command)
        valid_elements = None

        if pa_info:
            reject_regex = '.*(monitor|auto_null).*'
            valid_elements = [element for element in pa_info.splitlines()
                              if not re.match(reject_regex, element)]
        if not valid_elements:
            if self.logger:
                self.logger.error("No valid PulseAudio elements"
                                  " for %s" % (self.type))
            return None
        #We only need the pulseaudio numeric ID and long name for each element
        valid_elements = [(int(e.split()[0]), e.split()[1])
                          for e in valid_elements]
        return valid_elements[0]

    def _pactl_output(self, command):
        #This method mainly calls pactl (hence the name). Since pactl may
        #return a failure if the audio layer is not yet initialized, we will
        #try running a few times in case of failure. All our invocations of
        #pactl should be "idempotent" so repeating them should not have
        #any bad effects.
        for attempt in range(0, 3):
            try:
                return subprocess.check_output(command,
                                               universal_newlines=True)
            except (subprocess.CalledProcessError):
                time.sleep(5)
        return False
