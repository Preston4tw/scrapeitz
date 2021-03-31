import base64
import datetime
import sqlite3
import sys
import time
import urllib3

import dateutil.parser  # python-dateutil
from termcolor import colored
import requests  # requests

# Disable the warning with requests.get(url, verify=False)
# Not obvious why SSL doesn't work correctly but this workaround works so..
urllib3.disable_warnings()


def log(msg):
    print("{} {}".format(datetime.datetime.now().isoformat(timespec="seconds"), msg))


def readAuth():
    """
    Read the Javitz auth token out of the file 'auth'. The auth token is a
    base64 encoded object with a timestamp that indicates when the token
    expires. A warning message will be printed when the token is less than 2
    mins from expiration. If a new auth token is then placed in the auth file it
    will be read during program execution and allow the program to continue
    running with the new token. Otherwise the program will halt on a 400 HTTP
    error code.
    """
    with open("auth") as f:
        AUTH = f.read()
    AUTH_EXPIRATION = dateutil.parser.parse(eval(base64.b64decode(AUTH)).get("expiry"))
    return (AUTH, AUTH_EXPIRATION)


# To enable more verbose logging for requests
# import logging
# from http.client import HTTPConnection  # py3
# log = logging.getLogger('urllib3')
# log.setLevel(logging.DEBUG)
# # logging from urllib3 to console
# ch = logging.StreamHandler()
# ch.setLevel(logging.DEBUG)
# log.addHandler(ch)
# # print statements from `http.client.HTTPConnection` to console/stdout
# # HTTPConnection.debuglevel = 1


def seenNewAppointments(timestamp, con):
    log("New appointments seen at {}".format(timestamp))
    cur = con.cursor()
    cur.execute("insert into appointments_seen_at values (?)", (timestamp,))
    con.commit()


def recordAppointment(appointment, seenTime, con):
    guid, starttime = appointment.get("preregdateidGuid"), appointment.get("starttime")
    starttimeOutput = starttime
    """
    I had this set up for myself where I had my current appointment datetime in
    a text file, curappt. This would let me highlight the log messages for
    appointments that were earlier than the one I have, so I could trade up.
    """
    # appointmentStarttime = datetime.datetime.strptime(
    #     starttime, "%Y-%m-%dT%H:%M:%S.%f%z"
    # )
    # with open("curappt") as f:
    #     s, fmt = f.read(), "%B %d, %Y at %I:%M %p"
    #     currentAppointment = datetime.datetime.strptime(s, fmt).astimezone()
    # if appointmentStarttime < currentAppointment:
    #     starttimeOutput = colored(starttime, "red", "on_white")
    log("{} @ {}".format(guid, starttimeOutput))
    cur = con.cursor()
    cur.execute("insert into appointment values (?, ?, ?)", (guid, starttime, seenTime))
    con.commit()


def authExpiresWithin(timeDelta, authExpiration):
    return authExpiration - datetime.datetime.now(datetime.timezone.utc) <= timeDelta


def main():
    # Verify auth is still valid by timestamp
    AUTH, AUTH_EXPIRATION = readAuth()
    if AUTH_EXPIRATION < datetime.datetime.now(datetime.timezone.utc):
        log("auth expired before start: {}".format(AUTH_EXPIRATION.isoformat()))
        sys.exit(1)

    # Set up all the necessary headers. Pretend we're chrome. Copied directly
    # from "Copy as Curl" option of Chrome dev tools
    headers = {}
    headers["authority"] = "cdms2captcha.health.ny.gov"
    headers[
        "sec-ch-ua"
    ] = '"Google Chrome";v="89", "Chromium";v="89", ";Not A Brand";v="99"'
    headers["accept"] = "application/json, text/plain, */*"
    headers["authorization"] = AUTH
    headers["sec-ch-ua-mobile"] = "?0"
    headers[
        "user-agent"
    ] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_2_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
    headers["content-type"] = "application/json"
    headers["origin"] = "https://cdms2.health.ny.gov"
    headers["sec-fetch-site"] = "same-site"
    headers["sec-fetch-mode"] = "cors"
    headers["sec-fetch-dest"] = "empty"
    headers["referer"] = "https://cdms2.health.ny.gov/en-US/selectDateTime/times"
    headers["accept-language"] = "en-US,en;q=0.9"

    baseUrl = (
        "https://cdms2captcha.health.ny.gov/p/api/v1/appointment/available/event/date/"
    )
    url = "E9986975FF8F14BCE0530A6A7B166129"

    # Setup sqlite
    # This is nice for maybe later analysis.
    con = sqlite3.connect("javitz.sqlite3")
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS appointments_seen_at ( timestamp );")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS appointment ( preregdateidGuid, starttime, seenat );"
    )
    con.commit()

    log("start")

    while True:
        time.sleep(5) # this could maaaaybe be more aggressive
        if authExpiresWithin(datetime.timedelta(minutes=2), AUTH_EXPIRATION):
            log(
                "auth expiring soon: {}, attempting to grab new auth".format(
                    AUTH_EXPIRATION.isoformat()
                )
            )
            AUTH, AUTH_EXPIRATION = readAuth()
            headers["authorization"] = AUTH
        r = requests.get("{}{}".format(baseUrl, url), headers=headers, verify=False)
        appt = r.json().get("appointmentInfo")
        if not r.ok:
            log("request not ok, code {}".format(r.status_code))
            break
        if appt:
            seenTime = (
                datetime.datetime.now().astimezone().isoformat(timespec="seconds")
            )
            seenNewAppointments(seenTime, con)
            for a in appt:
                if a:
                    recordAppointment(a, seenTime, con)
        else:
            print(".", end="")
            sys.stdout.flush() # otherwise the dots don't print to console immediately


if __name__ == "__main__":
    main()
