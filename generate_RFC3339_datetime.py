import sys
import datetime
import re


PATTERN = re.compile(r"^(?P<past_flag>[-+])(?P<days>\d+d)?(?P<hours>\d+h)?(?P<minutes>\d+m)?$")

USAGE_TXT = """Usage:
python generate_RFC3339_datetime.py # prints current date-time in RFC3339
python generate_RFC3339_datetime.py -1d # prints date-time of a day ago in RFC3339
python generate_RFC3339_datetime.py +1m1d # prints date-time of 1 month 1 day in future in RFC3339
python generate_RFC3339_datetime.py -1m1d1m # prints date-time of 1 month 1 day 1 minute in the past in RFC3339
"""

def main(*args):
    
    if len(args) == 0:
        print(datetime.datetime.now(datetime.UTC).astimezone().isoformat())
        return 0
    
    if args[0] in ("-h", "--help"):
        print(USAGE_TXT, file=sys.stderr)
        return 130
    

    matched: re.Match = PATTERN.match(args[0])
    if matched is None:
        print(f"arg does not match {str(PATTERN)}", file=sys.stderr)
        return 1
    days = matched.group("days")
    hours = matched.group("hours")
    minutes = matched.group("minutes")
    past_flag = matched.group("past_flag")
    delta = datetime.timedelta(days=int(days[:-1]) if days else 0,
                               hours=int(hours[:-1]) if hours else 0,
                               minutes=int(minutes[:-1]) if minutes else 0)

    date_of_interest = datetime.datetime.now(datetime.UTC)
    if past_flag == "+":
        date_of_interest += delta
    if past_flag == "-":
        date_of_interest -= delta
    print(
        date_of_interest.astimezone().isoformat()
    )
    return 0

if __name__ == "__main__":
    sys.exit(
        main(*sys.argv[1:])
    )
