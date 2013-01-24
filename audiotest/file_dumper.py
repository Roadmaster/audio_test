#!/usr/bin/env python
class FileDumper(object):
    def write_to_file(self, filename, data):
        try:
            with open(filename, "wb") as f:
                for i in data:
                    print(i, file=f)
            return_value = True
        except (TypeError, IOError):
            return_value = False
        return return_value
