#!/usr/bin/env python3
# encoding: utf-8

__version__ = '0.5'

import re
import logging
import socket

import xml.etree.ElementTree as etree
import httplib

KEY_IDX_3D=400
KEY_IDX_ARROW_DOWN=2
KEY_IDX_ARROW_LEFT=3
KEY_IDX_ARROW_RIGHT=4
KEY_IDX_ARROW_UP=1
KEY_IDX_BACK=23
KEY_IDX_BLUE=29
KEY_IDX_BTN_1=5
KEY_IDX_BTN_2=6
KEY_IDX_BTN_3=7
KEY_IDX_BTN_4=8
KEY_IDX_CH_DOWN=28
KEY_IDX_CH_UP=27
KEY_IDX_ENTER=20
KEY_IDX_EXIT=412
KEY_IDX_EXTERNAL_INPUT=47
KEY_IDX_GREEN=30
KEY_IDX_HOME=21
KEY_IDX_MUTE=26
KEY_IDX_MYAPPS=417
KEY_IDX_NETCAST=408
KEY_IDX_PAUSE=34
KEY_IDX_PLAY=33
KEY_IDX_POWER_OFF=1
KEY_IDX_PREV_CHANNEL=403
KEY_IDX_RED=31
KEY_IDX_STOP=35
KEY_IDX_VOL_DOWN=25
KEY_IDX_VOL_UP=24
KEY_IDX_YELLOW=32

class KeyInputError(Exception):
    pass

class LGRemote:

    _xml_version_string = '<?xml version="1.0" encoding="utf-8"?>'
    _headers = {'Content-Type': 'application/atom+xml'}
    _highest_key_input_for_protocol = {'hdcp': 255, 'roap': 1024}

    def __init__(self, host=None, port=8080, protocol=None):

        self.port = int(port)
        self.host = host
        if host == None: self.getip()

        if protocol == None:
            self.auto_detect_accepted_protocol()
        else:
            self._protocol = protocol

        self._pairing_key = None
        self._session_id = None

    def getip(self):
        if self.host: return self.host
        strngtoXmit = 'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n' + \
            'MAN: "ssdp:discover"\r\nMX: 2\r\nST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n'

        bytestoXmit = strngtoXmit.encode()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        found = False
        i = 0

        while not found and i < 5:
            try:
                sock.sendto(bytestoXmit, ('239.255.255.250', 1900))
                gotbytes, addressport = sock.recvfrom(512)
                gotstr = gotbytes.decode()
                if re.search('LG', gotstr):
                    logging.debug('Returned: %s' % gotstr)
                    self.host, port = addressport
                    logging.debug('Found device: %s' % self.host)
                    found = True
                    break
                i += 1
            except:
                pass
        sock.close()

        if not found: raise socket.error("LG TV not found.")
        logging.info("Using device: %s over transport protocol: %s" % (self.host, self.port))
        return self.host

    def auto_detect_accepted_protocol(self):
        req_key_xml_string = self._xml_version_string + '<auth><type>AuthKeyReq</type></auth>'
        logging.debug("Detecting accepted protocol.")
        if self._doesServiceExist(3000):
            raise Exception("Protocol not supported. See https://github.com/ypid/lgcommander/issues/1")
        try:
            for protocol in self._highest_key_input_for_protocol:
                logging.debug("Testing protocol: %s" % (protocol))
                conn = httplib.HTTPConnection(self.host, port=self.port, timeout=3)
                conn.request("POST", "/%s/api/auth" % (protocol), req_key_xml_string, headers=self._headers)
                http_response = conn.getresponse()
                logging.debug("Got response: %s" % (http_response.reason))
                if http_response.reason == 'OK':
                    self._protocol = protocol
                    logging.debug("Using protocol: %s" % (self._protocol))
                    return self._protocol
            raise Exception("No accepted protocol found.")
        except:
            raise socket.error("No connection to host %s" % (self.host))

    def display_key_on_screen(self):
        conn = httplib.HTTPConnection(self.host, port=self.port)
        req_key_xml_string = self._xml_version_string + '<auth><type>AuthKeyReq</type></auth>'
        logging.debug("Request device to show key on screen.")
        conn.request('POST', '/%s/api/auth' % (self._protocol), req_key_xml_string, headers=self._headers)
        http_response = conn.getresponse()
        logging.debug("Device response was: %s" % (http_response.reason))
        if http_response.reason != "OK": raise Exception("Network error: %s" % (http_response.reason))

        return http_response.reason

    def get_session_id(self, paring_key):
        if not paring_key: return None

        self._pairing_key = paring_key
        logging.debug("Trying paring key: %s" % (self._pairing_key))
        pair_cmd_xml_string = self._xml_version_string + '<auth><type>AuthReq</type><value>' + \
            self._pairing_key + '</value></auth>'
        conn = httplib.HTTPConnection(self.host, port=self.port)
        conn.request('POST', '/%s/api/auth' % (self._protocol), pair_cmd_xml_string, headers=self._headers)
        http_response = conn.getresponse()
        if http_response.reason != 'OK': return None

        tree = etree.XML(http_response.read())
        self._session_id = tree.find('session').text
        logging.debug("Session ID is %s" % (self._session_id))
        if len(self._session_id) < 8: raise Exception("Could not get Session Id: %s" % (self._session_id))

        return self._session_id

    def handle_key_input(self, cmdcode):
        highest_key_input = self._highest_key_input_for_protocol[self._protocol]
        try:
            if 0 > int(cmdcode) or int(cmdcode) > highest_key_input:
                raise KeyInputError("Key input %s is not supported." % (cmdcode))
        except ValueError:
            raise KeyInputError("Key input %s is not a number" % (cmdcode))
        if not self._session_id: raise Exception("No valid session key available.")

        command_url_for_protocol = {
            'hdcp': '/%s/api/dtv_wifirc' % (self._protocol),
            'roap': '/%s/api/command' % (self._protocol),
        }

        logging.debug("Executing command: %s" % (cmdcode))
        key_input_xml_string = self._xml_version_string + '<command><session>' + self._session_id \
            + '</session><type>HandleKeyInput</type><value>' + cmdcode + '</value></command>'
        conn = httplib.HTTPConnection(self.host, port=self.port)
        conn.request('POST', command_url_for_protocol[self._protocol], key_input_xml_string, headers=self._headers)
        return conn.getresponse()

    def _doesServiceExist(self, port):
        try:
            logging.debug("Trying to connect to port %s" % (port))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((self.host, port))
            s.close()
        except:
            return False
        return True

def main():

    """Execute module in command line mode."""

    def get_pairing_key_from_user(lg_remote):
        lg_remote.display_key_on_screen()
        ####
        session_id='045855'
        return session_id

    args = ArgumentParser(
        description="Control your Smart Lg TV with your PC",
    )
    args.add_argument(
        '-V',
        '--version',
        action='version',
        version='%(prog)s {version}'.format(version=__version__)
    )
    args.add_argument(
        '-H',
        '--host',
        default='scan',
        help="IP address or FQDN of device."
        + " Use the special value \"scan\" for a multicast request for TVs in your LAN."
        + " \"scan\" will also be used if this parameter was omitted."
    )
    args.add_argument(
        '-p',
        '--port',
        default='8080',
        help="TCP port (default is 8080)."
    )
    args.add_argument(
        '-P',
        '--protocol',
        choices=['roap', 'hdcp'],
        default=None,
        help="Protocol to use."
        + " Currently ROAP and HDCP are supported."
        + " Default is to auto detect the correct one.",
    )
    args.add_argument(
        '-k',
        '--pairing-key',
        help="Pairing key of your TV."
        + " This key is shown on request on the screen"
        + " and does only change if you factory reset your TV."
    )
    args.add_argument(
        '-c',
        '--command',
        help="Send just a single command and exit."
    )
    user_parms = args.parse_args()

    logging.basicConfig(format='# %(levelname)s: %(message)s', level=logging.DEBUG)

    try:
        lg_remote = LGRemote(
            host=None if user_parms.host == 'scan' else user_parms.host,
            port=user_parms.port,
            protocol=user_parms.protocol)
    except socket.error as error:
        raise SystemExit(error)

    if user_parms.pairing_key:
        logging.debug("Pairing key from user %s" % (user_parms.pairing_key))
        lg_remote.get_session_id(user_parms.pairing_key)
    while not lg_remote._session_id:
        logging.debug("No valid pairing key available. Showing key on TV screen...")
        lg_remote.get_session_id(get_pairing_key_from_user(lg_remote))

    dialog_msg = "\nSession ID: " + str(lg_remote._session_id) + "\n"
    dialog_msg += "Paring key: " + str(lg_remote._pairing_key) + "\n"
    dialog_msg += "Success in establishing command session\n"
    dialog_msg += "_" * 64 + "\n\n"
    dialog_msg += "Some useful codes:\n"
    dialog_msg += "EZ_ADJUST menu:    255 \n"
    dialog_msg += "IN START menu:     251 \n"
    dialog_msg += "Installation menu: 207 \n"
    dialog_msg += "POWER_ONLY mode:   254 \n"
    dialog_msg += "_" * 64 + "\n\n"
    dialog_msg += "Warning: do not enter 254 if you \n"
    dialog_msg += "do not know what POWER_ONLY mode is. "

    logging.info(dialog_msg)

    if user_parms.command:
        lg_remote.handle_key_input(user_parms.command)
        raise SystemExit()

if __name__ == '__main__':
    from argparse import ArgumentParser
    main()