import configparser
import os
import sys


class ConfigManager:
    def __init__(self, config):

        print('Loading config: ' + config)

        config_file = os.path.join(os.getcwd(), config)
        if os.path.isfile(config_file):
            self.config = configparser.ConfigParser()
            self.config.read(config_file)
        else:
            print('ERROR: Unable To Load Config File: {}'.format(config_file))
            sys.exit(1)

        self._load_config_values()

        print('Configuration Successfully Loaded')

    def _load_config_values(self):

        # General
        self.delay = self.config['GENERAL'].getint('Delay', fallback=2)
        self.report_combined = self.config['GENERAL'].get('ReportCombined', fallback=True)

        # InfluxDB
        self.influx_address = self.config['INFLUXDB']['Address']
        self.influx_port = self.config['INFLUXDB'].getint('Port', fallback=8086)
        self.influx_database = self.config['INFLUXDB'].get('Database', fallback='plex_data')
        self.influx_ssl = self.config['INFLUXDB'].getboolean('SSL', fallback=False)
        self.influx_verify_ssl = self.config['INFLUXDB'].getboolean('Verify_SSL', fallback=True)
        self.influx_user = self.config['INFLUXDB'].get('Username', fallback='')
        self.influx_password = self.config['INFLUXDB'].get('Password', fallback='', raw=True)

        # Plex
        self.plex_user = self.config['PLEX']['Username']
        self.plex_password = self.config['PLEX'].get('Password', raw=True)
        plex_https = self.config['PLEX'].getboolean('HTTPS', fallback=False)
        self.conn_security = 'https' if plex_https else 'http'
        self.plex_verify_ssl = self.config['PLEX'].getboolean('Verify_SSL', fallback=False)
        servers = len(self.config['PLEX']['Servers'])

        # Logging
        self.logging_level = self.config['LOGGING']['Level'].upper()

        if servers:
            self.plex_server_addresses = self.config['PLEX']['Servers'].replace(' ', '').split(',')
        else:
            print('ERROR: No Plex Servers Provided.  Aborting')
            sys.exit(1)