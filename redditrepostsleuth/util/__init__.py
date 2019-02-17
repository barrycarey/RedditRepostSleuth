from redlock import RedLockFactory

redlock = RedLockFactory(
    connection_details=[
        {'host': '192.168.1.198', 'port': 6379, 'password': '@Password'}
    ])