class PIDController(object):
    """ A Proportional-Integrative-Derivative controller (PID) controls a
    process's output to try to maintain a desired output value (known as
    'setpoint', by continually adjusting the process's input.

    It does so by calculating the "error" (difference between output and
    setpoint) and attempting to minimize it manipulating the input.

    The desired change to the input is calculated based on error and three
    constants (Kp, Ki and Kd).  These values can be interpreted in terms of
    time: P depends on the present error, I on the accumulation of past errors,
    and D is a prediction of future errors, based on current rate of change.
    The weighted sum of these three actions is used to adjust the process via a
    control element.

    In practice, Kp, Ki and Kd are process-dependent and usually have to
    be tweaked by hand, but once reasonable constants are arrived at, they
    can apply to a particular process without further modification.

    """
    def __init__(self, Kp, Ki, Kd, setpoint=0):
        """ Creates a PID controller with given constants and setpoint.

           Arguments:
           Kp, Ki, Kd: PID constants, see class description.
           setpoint: desired output value; calls to input_change with
                     a process output reading will return a desired change
                     to the input to attempt matching output to this value.
        """
        self.setpoint = setpoint
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self._integral = 0
        self._previous_error = 0
        self._change_limit = 0

    def input_change(self, process_feedback, dt):
        """ Calculates desired input value change.

            Based on process feedback and time interval (dt).
        """
        error = self.setpoint - process_feedback
        self._integral = self._integral + (error * dt)
        derivative = (error - self._previous_error) / dt
        self._previous_error = error
        input_change = (self.Kp * error) + \
                       (self.Ki * self._integral) + \
                       (self.Kd * derivative)
        if self._change_limit and abs(input_change) > abs(self._change_limit):
            sign = input_change / abs(input_change)
            input_change = sign * self._change_limit
        return input_change

    def set_change_limit(self, limit):
        """Ensures that input value changes are lower than limit.

           Setting limit of zero disables this.
        """
        self._change_limit = limit

