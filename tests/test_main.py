
import json
import time

from typing import Any, Dict
from unittest.mock import mock_open, patch

import pytest
import responses

from responses import matchers

from py_gandi_dns_dynip.main import GANDI_LIVEDNS_BASE_URL, LOG_FMT
from py_gandi_dns_dynip.main import get_config, get_public_ip, get_record_ip, main, setup_logging, upsert_record


@pytest.fixture
def record_payload() -> Dict[str, Any]:
    return {
        'rrset_name': 'home',
        'rrset_ttl': 300,
        'rrset_type': 'A',
        'rrset_values': ['8.8.8.8'],
    }


@pytest.fixture
def config() -> Dict[str, Any]:
    return {
        'api_key': 'api_key',
        'domain': 'domain',
        'record': 'record',
    }


def test_setup_logging():
    with patch('py_gandi_dns_dynip.main.logging') as mock_logging:
        setup_logging()

    assert mock_logging.Formatter.converter == time.gmtime

    mock_logging.basicConfig.assert_called_once_with(level=mock_logging.DEBUG, format=LOG_FMT)

    mock_logging.getLogger.asser_called_once_with('urllib3')
    mock_logging.getLogger.return_value.setLevel.assert_called_once_with(mock_logging.WARNING)


def test_get_config_from_file_when_success_then_return_config():
    with patch('py_gandi_dns_dynip.main.open', mock_open(read_data='{"a": 1, "b": 2}')):
        config = get_config(['--config', 'config.json'])

    assert config == {'a': 1, 'b': 2}


@pytest.mark.parametrize('exception', [FileNotFoundError(), json.JSONDecodeError('', '', 0)])
def test_get_config_from_file_when_exception_then_raise_runtime_error(exception):
    with pytest.raises(RuntimeError):
        with patch('py_gandi_dns_dynip.main.open', side_effect=exception):
            get_config(['--config', 'config.json'])


def test_get_config_from_args_when_success_then_return_config():
    config = get_config(['--api-key', 'api_key', '--domain', 'domain', '--record', 'record', '--ip', 'ip'])

    assert config == {'api_key': 'api_key', 'domain': 'domain', 'record': 'record', 'ip': 'ip'}


def test_get_config_from_args_when_api_key_not_set_then_return_config_with_api_key_from_env():
    with patch('py_gandi_dns_dynip.main.os.getenv', return_value='api_key') as mock_os_getenv:
        config = get_config(['--domain', 'domain', '--record', 'record', '--ip', 'ip'])

    assert config == {'api_key': 'api_key', 'domain': 'domain', 'record': 'record', 'ip': 'ip'}

    mock_os_getenv.assert_called_once_with('GANDI_API_KEY')


@responses.activate
def test_get_public_ip_when_success_then_return_ip():
    responses.add(responses.GET, 'https://www.icanhazip.com/', body='8.8.8.8')

    public_ip = get_public_ip()

    assert public_ip == '8.8.8.8'


@responses.activate
def test_get_public_ip_when_not_200_then_return_none():
    responses.add(responses.GET, 'https://www.icanhazip.com/', status=500)

    assert get_public_ip() is None


@responses.activate
def test_get_public_ip_when_exception_then_return_none():
    assert get_public_ip() is None


@responses.activate
def test_get_public_ip_when_invalid_then_return_ip():
    responses.add(responses.GET, 'https://www.icanhazip.com/', body='a.a.a.a')

    assert get_public_ip() is None


@responses.activate
def test_get_record_ip_when_success_then_return_ip(record_payload):
    responses.add(responses.GET, f'{GANDI_LIVEDNS_BASE_URL}/domains/domain_name/records/domain_alias',
                  match=[matchers.header_matcher({'Authorization': 'Apikey api_key'})],
                  json=[record_payload])

    record_ip = get_record_ip('api_key', 'domain_name', 'domain_alias')

    assert record_ip == '8.8.8.8'


@responses.activate
def test_get_record_ip_when_multiple_records_then_return_none(record_payload):
    responses.add(responses.GET, f'{GANDI_LIVEDNS_BASE_URL}/domains/domain_name/records/domain_alias',
                  match=[matchers.header_matcher({'Authorization': 'Apikey api_key'})],
                  json=[record_payload, record_payload])

    assert get_record_ip('api_key', 'domain_name', 'domain_alias') is None


@responses.activate
def test_get_record_ip_when_type_mismatch_then_return_none(record_payload):
    record_payload['rrset_type'] = 'MX'

    responses.add(responses.GET, f'{GANDI_LIVEDNS_BASE_URL}/domains/domain_name/records/domain_alias',
                  match=[matchers.header_matcher({'Authorization': 'Apikey api_key'})],
                  json=[record_payload])

    assert get_record_ip('api_key', 'domain_name', 'domain_alias') is None


@responses.activate
def test_get_record_ip_when_multiple_values_then_return_none(record_payload):
    record_payload['rrset_values'] = ['8.8.8.8', '4.4.4.4']

    responses.add(responses.GET, f'{GANDI_LIVEDNS_BASE_URL}/domains/domain_name/records/domain_alias',
                  match=[matchers.header_matcher({'Authorization': 'Apikey api_key'})],
                  json=[record_payload])

    assert get_record_ip('api_key', 'domain_name', 'domain_alias') is None


@responses.activate
def test_get_record_ip_when_not_present_then_return_none():
    responses.add(responses.GET, f'{GANDI_LIVEDNS_BASE_URL}/domains/domain_name/records/domain_alias',
                  match=[matchers.header_matcher({'Authorization': 'Apikey api_key'})],
                  json=[])

    assert get_record_ip('api_key', 'domain_name', 'domain_alias') is None


@responses.activate
def test_get_record_ip_when_not_200_then_return_none():
    responses.add(responses.GET, f'{GANDI_LIVEDNS_BASE_URL}/domains/domain_name/records/domain_alias', status=500)

    assert get_record_ip('api_key', 'domain_name', 'domain_alias') is None


@responses.activate
def test_get_record_ip_when_exception_then_return_none():
    assert get_record_ip('api_key', 'domain_name', 'domain_alias') is None


@responses.activate
def test_upsert_record_when_success_then_return_true():
    responses.add(responses.PUT, f'{GANDI_LIVEDNS_BASE_URL}/domains/domain_name/records/domain_alias', status=201,
                  match=[matchers.json_params_matcher(
                      {
                          'items': [
                              {
                                  'rrset_ttl': 300,
                                  'rrset_type': 'A',
                                  'rrset_values': ['8.8.8.8'],
                              }
                          ]
                      }
                  )])

    assert upsert_record('api_key', 'domain_name', 'domain_alias', '8.8.8.8')


@responses.activate
def test_upsert_record_when_not_201_then_return_false():
    responses.add(responses.PUT, f'{GANDI_LIVEDNS_BASE_URL}/domains/domain_name/records/domain_alias', status=500)

    assert not upsert_record('api_key', 'domain_name', 'domain_alias', '8.8.8.8')


@responses.activate
def test_upsert_record_when_exception_then_return_false():
    assert not upsert_record('api_key', 'domain_name', 'domain_alias', '8.8.8.8')


def test_main_when_success_then_return_zero(config):
    with patch('py_gandi_dns_dynip.main.setup_logging') as mock_setup_logging, \
            patch('py_gandi_dns_dynip.main.get_config', return_value=config) as mock_get_config, \
            patch('py_gandi_dns_dynip.main.get_public_ip', return_value='8.8.8.8') as mock_get_public_ip, \
            patch('py_gandi_dns_dynip.main.get_record_ip', return_value='4.4.4.4') as mock_get_record_ip, \
            patch('py_gandi_dns_dynip.main.upsert_record', return_value=True) as mock_upsert_record:
        rc = main(['--config', 'config.json'])

    assert rc == 0

    mock_setup_logging.assert_called_once()

    mock_get_config.assert_called_once_with(['--config', 'config.json'])

    mock_get_public_ip.assert_called_once()

    mock_get_record_ip.assert_called_once_with(config['api_key'], config['domain'], config['record'])

    mock_upsert_record.assert_called_once_with(config['api_key'], config['domain'], config['record'], '8.8.8.8')


def test_main_when_ip_in_config_then_use_config_ip_and_return_zero(config):
    config['ip'] = '1.2.3.4'

    with patch('py_gandi_dns_dynip.main.setup_logging') as mock_setup_logging, \
            patch('py_gandi_dns_dynip.main.get_config', return_value=config) as mock_get_config, \
            patch('py_gandi_dns_dynip.main.get_public_ip') as mock_get_public_ip, \
            patch('py_gandi_dns_dynip.main.get_record_ip', return_value='4.4.4.4') as mock_get_record_ip, \
            patch('py_gandi_dns_dynip.main.upsert_record', return_value=True) as mock_upsert_record:
        rc = main(['--config', 'config.json'])

    assert rc == 0

    mock_setup_logging.assert_called_once()

    mock_get_config.assert_called_once_with(['--config', 'config.json'])

    mock_get_public_ip.assert_not_called()

    mock_get_record_ip.assert_called_once_with(config['api_key'], config['domain'], config['record'])

    mock_upsert_record.assert_called_once_with(config['api_key'], config['domain'], config['record'], '1.2.3.4')


def test_main_when_ip_match_then_do_not_upsert_and_return_zero(config):
    with patch('py_gandi_dns_dynip.main.setup_logging') as mock_setup_logging, \
            patch('py_gandi_dns_dynip.main.get_config', return_value=config) as mock_get_config, \
            patch('py_gandi_dns_dynip.main.get_public_ip', return_value='8.8.8.8') as mock_get_public_ip, \
            patch('py_gandi_dns_dynip.main.get_record_ip', return_value='8.8.8.8') as mock_get_record_ip, \
            patch('py_gandi_dns_dynip.main.upsert_record') as mock_upsert_record:
        rc = main(['--config', 'config.json'])

    assert rc == 0

    mock_setup_logging.assert_called_once()

    mock_get_config.assert_called_once_with(['--config', 'config.json'])

    mock_get_public_ip.assert_called_once()

    mock_get_record_ip.assert_called_once_with(config['api_key'], config['domain'], config['record'])

    mock_upsert_record.assert_not_called()


def test_main_when_no_record_then_create_and_return_zero(config):
    with patch('py_gandi_dns_dynip.main.setup_logging') as mock_setup_logging, \
            patch('py_gandi_dns_dynip.main.get_config', return_value=config) as mock_get_config, \
            patch('py_gandi_dns_dynip.main.get_public_ip', return_value='8.8.8.8') as mock_get_public_ip, \
            patch('py_gandi_dns_dynip.main.get_record_ip', return_value=None) as mock_get_record_ip, \
            patch('py_gandi_dns_dynip.main.upsert_record', return_value=True) as mock_upsert_record:
        rc = main(['--config', 'config.json'])

    assert rc == 0

    mock_setup_logging.assert_called_once()

    mock_get_config.assert_called_once_with(['--config', 'config.json'])

    mock_get_public_ip.assert_called_once()

    mock_get_record_ip.assert_called_once_with(config['api_key'], config['domain'], config['record'])

    mock_upsert_record.assert_called_once_with(config['api_key'], config['domain'], config['record'], '8.8.8.8')


def test_main_when_no_public_ip_then_return_one(config):
    with patch('py_gandi_dns_dynip.main.setup_logging') as mock_setup_logging, \
            patch('py_gandi_dns_dynip.main.get_config', return_value=config) as mock_get_config, \
            patch('py_gandi_dns_dynip.main.get_public_ip', return_value=None) as mock_get_public_ip, \
            patch('py_gandi_dns_dynip.main.get_record_ip') as mock_get_record_ip, \
            patch('py_gandi_dns_dynip.main.upsert_record') as mock_upsert_record:
        rc = main(['--config', 'config.json'])

    assert rc == 1

    mock_setup_logging.assert_called_once()

    mock_get_config.assert_called_once_with(['--config', 'config.json'])

    mock_get_public_ip.assert_called_once()

    mock_get_record_ip.assert_not_called()

    mock_upsert_record.assert_not_called()


def test_main_when_incomplete_config_then_return_one():
    with patch('py_gandi_dns_dynip.main.setup_logging') as mock_setup_logging, \
            patch('py_gandi_dns_dynip.main.get_config', return_value={}) as mock_get_config, \
            patch('py_gandi_dns_dynip.main.get_public_ip') as mock_get_public_ip, \
            patch('py_gandi_dns_dynip.main.get_record_ip') as mock_get_record_ip, \
            patch('py_gandi_dns_dynip.main.upsert_record') as mock_upsert_record:
        rc = main(['--config', 'config.json'])

    assert rc == 1

    mock_setup_logging.assert_called_once()

    mock_get_config.assert_called_once_with(['--config', 'config.json'])

    mock_get_public_ip.assert_not_called()

    mock_get_record_ip.assert_not_called()

    mock_upsert_record.assert_not_called()


def test_main_when_upsert_fails_then_return_1(config):
    with patch('py_gandi_dns_dynip.main.setup_logging') as mock_setup_logging, \
            patch('py_gandi_dns_dynip.main.get_config', return_value=config) as mock_get_config, \
            patch('py_gandi_dns_dynip.main.get_public_ip', return_value='8.8.8.8') as mock_get_public_ip, \
            patch('py_gandi_dns_dynip.main.get_record_ip', return_value='4.4.4.4') as mock_get_record_ip, \
            patch('py_gandi_dns_dynip.main.upsert_record', return_value=False) as mock_upsert_record:
        rc = main(['--config', 'config.json'])

    assert rc == 1

    mock_setup_logging.assert_called_once()

    mock_get_config.assert_called_once_with(['--config', 'config.json'])

    mock_get_public_ip.assert_called_once()

    mock_get_record_ip.assert_called_once_with(config['api_key'], config['domain'], config['record'])

    mock_upsert_record.assert_called_once_with(config['api_key'], config['domain'], config['record'], '8.8.8.8')
