#!/usr/bin/env python

import platform
import logging
import os
import sys

if sys.version_info.major == 2:
    import gobject
else:
    from gi.repository import GLib as gobject
import time
import requests
import configparser
import dbus

sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService


class DbusEvccChargerService:
    def __init__(self, servicename, paths, loadpoint_index, productname='EVCC-Charger', connection='EVCC REST API'):
        config = self._getConfig()
        section = 'LOADPOINT{}'.format(loadpoint_index)
        if config.has_section(section):
            deviceinstance = int(config[section]['Deviceinstance'])
        else:
            deviceinstance = int(config['DEFAULT']['Deviceinstance']) + loadpoint_index

        self._loadpoint_index = loadpoint_index
        _bus = dbus.SystemBus(private=True)
        self._dbusservice = VeDbusService('{}.http_{:02d}'.format(servicename, deviceinstance), bus=_bus)
        self._paths = paths

        logging.debug('%s /DeviceInstance = %d' % (servicename, deviceinstance))

        self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self._dbusservice.add_path('/Mgmt/ProcessVersion',
                                   'Unkown version, and running on Python ' + platform.python_version())
        self._dbusservice.add_path('/Mgmt/Connection', connection)
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        self._dbusservice.add_path('/ProductId', 0xFFFF)
        self._dbusservice.add_path('/ProductName', productname)
        custom_name = config[section].get('Name', '') if config.has_section(section) else ''
        if not custom_name:
            custom_name = '{} {}'.format(productname, loadpoint_index + 1)
        self._dbusservice.add_path('/CustomName', custom_name)
        self._dbusservice.add_path('/HardwareVersion', 2)
        self._dbusservice.add_path('/Connected', 1)
        self._dbusservice.add_path('/UpdateIndex', 0)
        self._dbusservice.add_path('/Position', 1)

        for path in ['/Status', '/Mode']:
            self._dbusservice.add_path(path, None)

        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path, settings['initial'], gettextcallback=settings['textformat'], writeable=False)

        self._lastUpdate = 0

    def _getConfig(self):
        config = configparser.ConfigParser()
        config.read('%s/config.ini' % (os.path.dirname(os.path.realpath(__file__))))
        return config

    def _getSignOfLifeInterval(self):
        config = self._getConfig()
        value = config['DEFAULT'].get('SignOfLifeLog', '1')
        return int(value) if value else 1

    def _getEvccStatusUrl(self):
        config = self._getConfig()
        accessType = config['DEFAULT']['AccessType']
        if accessType == 'OnPremise':
            return 'http://%s/api/state' % config['ONPREMISE']['Host']
        raise ValueError('AccessType %s is not supported' % accessType)

    def _getEvccChargerData(self):
        URL = self._getEvccStatusUrl()
        request_data = requests.get(url=URL)
        if not request_data:
            raise ConnectionError('No response from EVCC - %s' % URL)
        json_data = request_data.json()
        if not json_data:
            raise ValueError('Converting response to JSON failed')
        return json_data

    def signOfLife(self):
        logging.info('--- Start: sign of life (loadpoint %d) ---' % self._loadpoint_index)
        logging.info('Last _update() call: %s' % self._lastUpdate)
        logging.info("Last '/Ac/Power': %s" % self._dbusservice['/Ac/Power'])
        logging.info('--- End: sign of life ---')
        return True

    def update(self, loadpoints):
        try:
            if self._loadpoint_index >= len(loadpoints):
                logging.warning('Loadpoint %d not available (only %d found)' % (
                    self._loadpoint_index, len(loadpoints)))
                return True
            loadpoint = loadpoints[self._loadpoint_index]

            voltage = 230
            currents = loadpoint.get('chargeCurrents', [0, 0, 0])
            self._dbusservice['/Ac/L1/Power'] = float(currents[0]) * voltage
            self._dbusservice['/Ac/L2/Power'] = float(currents[1]) * voltage
            self._dbusservice['/Ac/L3/Power'] = float(currents[2]) * voltage
            self._dbusservice['/Ac/Voltage'] = voltage
            self._dbusservice['/Ac/Power'] = float(loadpoint['chargePower'])
            self._dbusservice['/Current'] = max(currents)
            self._dbusservice['/SetCurrent'] = float(loadpoint.get('offeredCurrent', 0))
            self._dbusservice['/MaxCurrent'] = int(loadpoint['maxCurrent'])

            if 'pv' in loadpoint['mode']:
                self._dbusservice['/Mode'] = 1
                self._dbusservice['/StartStop'] = 1
            elif loadpoint['mode'] == 'off':
                self._dbusservice['/Mode'] = 0
                self._dbusservice['/StartStop'] = 0
            else:
                self._dbusservice['/Mode'] = 0
                self._dbusservice['/StartStop'] = 1

            status = 0
            if not loadpoint.get('connected', False):
                status = 0
            elif loadpoint.get('charging', False):
                status = 2
            else:
                status = 1
            self._dbusservice['/Status'] = status

            if status == 0:
                self._dbusservice['/Ac/Energy/Forward'] = 0
                self._dbusservice['/Session/Energy'] = 0
                self._dbusservice['/ChargingTime'] = 0
                self._dbusservice['/Session/Time'] = 0
            else:
                self._dbusservice['/Ac/Energy/Forward'] = float(loadpoint.get('chargedEnergy', 0)) / 1000
                self._dbusservice['/Session/Energy'] = self._dbusservice['/Ac/Energy/Forward']
                self._dbusservice['/ChargingTime'] = int(loadpoint.get('chargeDuration', 0))
                self._dbusservice['/Session/Time'] = self._dbusservice['/ChargingTime']

            logging.debug('LP%d /Ac/Power: %s' % (self._loadpoint_index, self._dbusservice['/Ac/Power']))
            logging.debug('LP%d /Ac/Energy/Forward: %s' % (self._loadpoint_index, self._dbusservice['/Ac/Energy/Forward']))

            index = self._dbusservice['/UpdateIndex'] + 1
            if index > 255:
                index = 0
            self._dbusservice['/UpdateIndex'] = index
            self._lastUpdate = time.time()
        except Exception as e:
            logging.critical('Error at update (loadpoint %d)' % self._loadpoint_index, exc_info=e)
        return True


def make_paths(_kwh, _a, _w, _v, _s):
    return {
        '/Ac/Power':          {'initial': 0,    'textformat': _w},
        '/Ac/L1/Power':       {'initial': 0,    'textformat': _w},
        '/Ac/L2/Power':       {'initial': 0,    'textformat': _w},
        '/Ac/L3/Power':       {'initial': 0,    'textformat': _w},
        '/Ac/Energy/Forward': {'initial': 0,    'textformat': _kwh},
        '/Session/Energy':    {'initial': None, 'textformat': _kwh},
        '/Session/Time':      {'initial': None, 'textformat': _s},
        '/ChargingTime':      {'initial': 0,    'textformat': _s},
        '/Ac/Voltage':        {'initial': 0,    'textformat': _v},
        '/Current':           {'initial': 0,    'textformat': _a},
        '/SetCurrent':        {'initial': 0,    'textformat': _a},
        '/MaxCurrent':        {'initial': 0,    'textformat': _a},
        '/StartStop':         {'initial': 0,    'textformat': lambda p, v: str(v)},
    }


def update_all_services(services):
    try:
        data = services[0]._getEvccChargerData()
        loadpoints = data['loadpoints']
        for service in services:
            service.update(loadpoints)
    except Exception as e:
        logging.critical('Error fetching evcc data', exc_info=e)
    return True


def sign_of_life_all_services(services):
    for service in services:
        service.signOfLife()
    return True


def main():
    logging.basicConfig(
        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.INFO,
        handlers=[
            logging.FileHandler('%s/current.log' % os.path.dirname(os.path.realpath(__file__))),
            logging.StreamHandler()
        ])

    try:
        logging.info('Start')
        from dbus.mainloop.glib import DBusGMainLoop
        DBusGMainLoop(set_as_default=True)

        _kwh = lambda p, v: str(round(v, 2)) + 'kWh'
        _a   = lambda p, v: str(round(v, 1)) + 'A'
        _w   = lambda p, v: str(round(v, 1)) + 'W'
        _v   = lambda p, v: str(round(v, 1)) + 'V'
        _s   = lambda p, v: str(v) + 's'

        config = configparser.ConfigParser()
        config.read('%s/config.ini' % os.path.dirname(os.path.realpath(__file__)))
        host = config['ONPREMISE']['Host']
        data = requests.get('http://{}/api/state'.format(host)).json()
        lp_sections=sorted([s for s in config.sections() if s.upper().startswith('LOADPOINT')])
        api_count=len(data['loadpoints'])
        if lp_sections:
            num_loadpoints=min(len(lp_sections), api_count)
            logging.info('Config has %d loadpoint(s), API has %d, using %d' % (len(lp_sections), api_count, num_loadpoints))
        else:
            num_loadpoints=api_count
            logging.info('Auto-detected %d loadpoint(s) from API' % num_loadpoints)

        services = []
        for i in range(num_loadpoints):
            svc = DbusEvccChargerService(
                servicename='com.victronenergy.evcharger',
                paths=make_paths(_kwh, _a, _w, _v, _s),
                loadpoint_index=i,
            )
            services.append(svc)
            logging.info('Registered loadpoint %d on D-Bus' % i)

        sign_interval = services[0]._getSignOfLifeInterval() if services else 1
        gobject.timeout_add(sign_interval * 60 * 1000, sign_of_life_all_services, services)
        gobject.timeout_add(2000, update_all_services, services)

        logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
        mainloop = gobject.MainLoop()
        mainloop.run()
    except Exception as e:
        logging.critical('Error at %s', 'main', exc_info=e)


if __name__ == '__main__':
    main()
