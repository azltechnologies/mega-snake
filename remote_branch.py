"""Class Module representing a remote branch"""
import dataclasses
import datetime

@dataclasses.dataclass
class RemoteBranch:
    """Class containing a named set of properties"""

    merged_on_master: bool
    commit: str
    date_str: str
    # Parse the string into a datetime object
    parsed_datetime: datetime
    mail: str
    branch: str
    message: str

    def __init__(self, input_string: str):
        if input_string is not None and bool(input_string):
            result = input_string.split("|")
            result = [value.strip() for value in result]
            print(result)
            self.merged_on_master = bool(int(result[0]))
            self.commit = result[1]
            self.date_str = result[2]
            self.parsed_datetime = datetime.datetime.strptime(self.date_str, "%Y-%m-%dT%H:%M:%SZ")
            self.mail = result[3]
            self.branch = result[4]
            if len(result) <= 6:
                print ('SEÑALLLLLLLLL')
                self.message = result[5]
