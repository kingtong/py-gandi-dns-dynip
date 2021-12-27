
# gandi-dns-dynip

Little tool to set an `A` record on a domain registered with Gandi.

The public IP set for the record is determined with [https://www.icanhazip.com/]() or by setting it manually from command line or configuration file.

## Installing

```
pip install py-gandi-dns-dynip
```
## Usage

```
usage: main.py [-h] [--config CONFIG] [--api-key API_KEY] [--domain DOMAIN] [--record RECORD] [--ip IP]

Set Gandi DNS record with local public IP

optional arguments:
  -h, --help         show this help message and exit
  --config CONFIG    Path to config file (format: JSON, keys: api_key, domain, record, ip)
  --api-key API_KEY  API key for Gandi (can also be set through env var GANDI_API_KEY)
  --domain DOMAIN    Domain registered with Gandi
  --record RECORD    Record (A) name to associate with the public IP
  --ip IP            Force public IP (useful for tests or icanhazip.com unavailability)
```

## Configuration

The configuration file is a basic JSON file with the following structure:

```json
{
    "api_key": "gandi_api_key",
    "domain": "domain_name",
    "record": "domain_record_name",
    "ip": "ip (optional)"
}
```

## Reference
* https://www.gandi.net/
* https://api.gandi.net/docs/
* https://www.icanhazip.com/
