
import argparse
import ipaddress
import json
import logging
import os
import sys
import time

from typing import Any, Dict, List, Optional

import requests

from requests.exceptions import RequestException

GANDI_LIVEDNS_BASE_URL = 'https://api.gandi.net/v5/livedns'
GANDI_RECORD_TTL = 300

LOG = logging.getLogger('gandy-dns-dynip')
LOG_FMT = '%(asctime)-15s:%(name)s:%(levelname)s:%(message)s'


def setup_logging():
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(level=logging.DEBUG, format=LOG_FMT)

    logging.getLogger('urllib3').setLevel(logging.WARNING)


def get_config(args: List[str]) -> Dict[str, Any]:
    """
    Build config from command line arguments.

    :param args: Command line arguments
    :return: The config dictionary
    """
    parser = argparse.ArgumentParser(description='Set Gandi DNS record with local public IP')
    parser.add_argument('--config', dest='config',
                        help='Path to config file (format: JSON, keys: api_key, domain, record, ip)')
    parser.add_argument('--api-key', dest='api_key',
                        help='API key for Gandi (can also be set through env var GANDI_API_KEY)')
    parser.add_argument('--domain', dest='domain',
                        help='Domain registered with Gandi')
    parser.add_argument('--record', dest='record',
                        help='Record (A) name to associate with the public IP')
    parser.add_argument('--ip', dest='ip',
                        help='Force public IP (useful for tests or if https://www.icanhazip.com is not available)')

    args = parser.parse_args(args)

    if args.config:
        try:
            with open(args.config, 'r') as f_in:
                config = json.load(f_in)
        except (OSError, json.JSONDecodeError) as err:
            raise RuntimeError(f'Cannot parse config file {args.config}: {err}')
    else:
        config = {
            'api_key': args.api_key or os.getenv('GANDI_API_KEY'),
            'domain': args.domain,
            'record': args.record,
            'ip': args.ip
        }

    return config


def get_public_ip() -> Optional[str]:
    """
    Fetch public IP using external service.

    :return: The public IP
    """
    public_ip: Optional[str] = None

    try:
        resp = requests.get('https://www.icanhazip.com/')

        if resp.status_code != 200:
            LOG.error(f'Unexpected response while fetching public IP: {resp.status_code} - {resp.text}')
        else:
            public_ip = resp.text.strip()

            # Validate IP address
            ipaddress.ip_address(public_ip)
    except RequestException as err:
        LOG.error(f'Unexpected exception while fetching public IP: {err}')
    except ValueError as err:
        LOG.error(f'Invalid fetched public IP {public_ip}: {err}')
        public_ip = None

    return public_ip


def get_record_ip(api_key: str, domain: str, record: str) -> Optional[str]:
    """
    Retrieve IP registered for domain_alias.

    :param api_key: API key
    :param domain: Domain name
    :param record: Domain record
    :return: The record IP
    """
    record_ip: Optional[str] = None

    try:
        resp = requests.get(f'{GANDI_LIVEDNS_BASE_URL}/domains/{domain}/records/{record}',
                            headers={'Authorization': f'Apikey {api_key}'})

        if resp.status_code == 200:
            resp_payload = resp.json()
            if len(resp_payload) == 0:
                LOG.debug(f'Record {record}.{domain} is not declared')
                return None

            if len(resp_payload) != 1:
                raise RuntimeError(f'Multiple records for {record}.{domain}')

            record = resp_payload[0]
            if record['rrset_type'] != 'A':
                raise RuntimeError(f'Record {record}.{domain} is not an alias: {record["rrset_type"]}')

            if len(record['rrset_values']) != 1:
                raise RuntimeError(f'Multiple values for {record}.{domain}: {record["rrset_values"]}')

            record_ip = record['rrset_values'][0]
        else:
            LOG.error(f'Unexpected response while fetching IP for {record}.{domain}: '
                      f'{resp.status_code} - {resp.text}')
    except RequestException as err:
        LOG.error(f'Unexpected exception while fetching record IP: {err}')
    except RuntimeError as err:
        LOG.error(f'Unexpected error while fetching record IP: {err}')
        record_ip = None

    return record_ip


def upsert_record(api_key: str, domain: str, record: str, ip: str) -> bool:
    """
    Create or update domain record.

    :param api_key: API key
    :param domain: Domain name
    :param record: Domain record
    :param ip: Record IP
    :return: The status
    """
    success = True

    try:
        resp = requests.put(f'{GANDI_LIVEDNS_BASE_URL}/domains/{domain}/records/{record}',
                            headers={'Authorization': f'Apikey {api_key}'},
                            json={
                                'items': [
                                    {
                                        'rrset_type': 'A',
                                        'rrset_values': [ip],
                                        'rrset_ttl': GANDI_RECORD_TTL,
                                    }
                                ]
                            })

        if resp.status_code != 201:
            LOG.error(f'Unexpected response while setting record {record}.{domain}: '
                      f'{resp.status_code} - {resp.text}')
            success = False
    except RequestException as err:
        LOG.error(f'Unexpected exception while fetching record IP: {err}')
        success = False

    return success


def main(args: Optional[List[str]] = None) -> int:
    """
    Set Gandi DNS record with local public IP.

    :param args: Command line arguments
    :return: The status code
    """
    setup_logging()

    config = get_config(args)

    if not all(k in config for k in ['api_key', 'domain', 'record']):
        LOG.error(f'Incomplete config: {config.keys()}')
        return 1

    # Fetch public IP
    if 'ip' in config:
        LOG.debug('Using config for public IP')
        public_ip = config['ip']
    else:
        LOG.debug('Getting public IP')
        public_ip = get_public_ip()

    if public_ip is None:
        LOG.error('Cannot find public IP')
        return 1

    LOG.debug(f'Public IP found: {public_ip}')

    # Fetch record IP
    LOG.debug('Getting record IP')

    gandi_ip = get_record_ip(config['api_key'], config['domain'], config['record'])

    LOG.debug(f'Record IP found: {gandi_ip}')

    # Compute update
    rc = 0
    if gandi_ip == public_ip:
        LOG.debug('IPs are matching')
    else:
        if gandi_ip is None:
            LOG.debug(f'Setting new record {config["record"]}.{config["domain"]} with IP {public_ip}')
        else:
            LOG.debug(f'Updating record {config["record"]}.{config["domain"]} with IP {public_ip}')

        # Create or update record
        if upsert_record(config['api_key'], config['domain'], config['record'], public_ip):
            LOG.info(f'Record {config["record"]}.{config["domain"]} set with IP {public_ip}')
        else:
            LOG.error(f'Failure setting record {config["record"]}.{config["domain"]} with IP {public_ip}')
            rc = 1

    return rc


if __name__ == '__main__':
    exit(main(sys.argv[1:]))  # pragma: no cover
