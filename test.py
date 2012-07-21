#!/usr/bin/env python
import unittest
import pa

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


if __name__ == '__main__':
    unittest.main()
