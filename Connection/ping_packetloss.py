import os
import ping3
import sqlite3
import time

database_file = 'db.sqlite3'

# Specify the IP address you want to ping
ip_address = '8.8.8.8'


def create_database():
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS packet_loss (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            error_message TEXT
        )
    ''')

    conn.commit()
    conn.close()

def ping_and_store(ip_address):
    create_database()

    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    while True:
        try:
            ping_time = ping3.ping(ip_address)
            if ping_time is None or ping_time > 0.5:
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                error_message = 'Timeout' if ping_time is None else 'Ping time exceeded 500ms'
                cursor.execute('INSERT INTO packet_loss (timestamp, error_message) VALUES (?, ?)', (timestamp, error_message))
                conn.commit()
                print('Ping failed:', timestamp, error_message)
            else:
                print('Ping success:', round(ping_time * 1000, 2), 'ms')
        except Exception as e:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('INSERT INTO packet_loss (timestamp, error_message) VALUES (?, ?)', (timestamp, str(e)))
            conn.commit()
            print('Ping failed:', timestamp, str(e))

        time.sleep(5)

    conn.close()

ping_and_store(ip_address)