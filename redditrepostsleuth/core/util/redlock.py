from redlock import RedLockFactory

# TODO - Cleanup the init of this
redlock = RedLockFactory(
    connection_details=[
        {'host': '192.168.1.198', 'port': 6379, 'password': '@Password', 'db': 1}
    ])