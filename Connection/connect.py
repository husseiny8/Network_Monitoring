import socket
import os
import datetime
import time

FILE = os.path.join(os.getcwd(), "networkinfo.log")

# This function will only be executed once, i.e.
# at the beginning of the script
# to check if the system is already connected to an internet connection or not
def first_check():
    # to check if the machine already have a live internet connection
    # if ping returns true
    if ping():
        live = "\nCONNECTION ACQUIRED\n"
        print(live)
        connection_acquired_time = datetime.datetime.now()
        acquiring_message = "connection acquired at: " + \
            str(connection_acquired_time).split(".")[0] + "\n"
        print(acquiring_message)

        # writes into the log file
        with open(FILE, "a") as file:
            file.write(live)
            file.write(acquiring_message)
        return True

    # if ping returns false
    else:
        not_live = "\nCONNECTION NOT ACQUIRED\n"
        print(not_live)

        # writes into the log file
        with open(FILE, "a") as file:
            file.write(not_live)
        return False



def ping():
    # to ping a particular PORT at an IP
    # if the machine won't receive any packets from
    # the server for more than 3 seconds
    # i.e no connection is
    # made(machine doesn't have a live internet connection)
    # <except> part will be executed
    try:
        # if we do not get any response from the server for more than 5 seconds,
        # the connection is not made.
        socket.setdefaulttimeout(5)

        # AF_INET: address family (IPv4)
        # SOCK_STREAM: type for TCP (PORT)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        host = "8.8.8.8"
        port = 53

        server_address = (host, port)

        # send connection request to the defined server
        s.connect(server_address)

    except OSError as error:

        # function returning false after
        # data interruption(no connection)
        return False
    else:

        # the connection is closed after
        # machine being connected
        s.close()
        return True


def calculate_time(start, stop):
    # to calculate unavailability time
    difference = stop - start
    seconds = float(str(difference.total_seconds()))
    return str(datetime.timedelta(seconds=seconds)).split(".")[0]


def main():
    # MAIN
    monitor_start_time = datetime.datetime.now()

    # monitoring time is when the script
    # started monitoring internet connection status
    monitoring_date_time = "monitoring started at: " + \
                           str(monitor_start_time).split(".")[0]

    if first_check():
        # if true
        print(monitoring_date_time)

        # monitoring will only start when
        # the connection will be acquired

    else:
        # if false
        while True:

            # infinite loop to check if the connection is acquired
            # will run until there is a live internet connection
            if not ping():

                # if connection not acquired
                time.sleep(1)
            else:

                # if connection is acquired
                first_check()
                print(monitoring_date_time)
                break

            with open(FILE, "a") as file:
                # writes into the log file
                file.write("\n")
                file.write(monitoring_date_time + "\n")

    while True:

        # FIRST WHILE, infinite loop,
        # will run until the machine is on
        # or the script is manually terminated
        if ping():
            # if true: the loop will execute after every 5 seconds
            time.sleep(5)

        else:

            # if false: fail message will be displayed
            down_time = datetime.datetime.now()
            fail_msg = "disconnected at: " + str(down_time).split(".")[0]
            print(fail_msg)

            with open(FILE, "a") as file:
                # writes into the log file
                file.write(fail_msg + "\n")

            while not ping():
                # infinite loop,
                # will run till ping() return true
                time.sleep(1)

            up_time = datetime.datetime.now()

            # will execute after while true is
            # false (connection restored)
            uptime_message = "connected again: " + str(up_time).split(".")[0]

            down_time = calculate_time(down_time, up_time)

            # calling time calculating
            # function, printing down time
            unavailablity_time = "connection was unavailable for: " + down_time

            print(uptime_message)
            print(unavailablity_time)

            with open(FILE, "a") as file:

                # log entry for connected restoration time,
                # and unavailability time
                file.write(uptime_message + "\n")
                file.write(unavailablity_time + "\n")

main()