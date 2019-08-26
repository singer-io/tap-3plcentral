#!/usr/bin/env python3

import sys
import json
import argparse
import singer
from singer import metadata, utils
from tap_3plcentral.client import TPLClient
from tap_3plcentral.discover import discover
from tap_3plcentral.sync import sync

LOGGER = singer.get_logger()

REQUIRED_CONFIG_KEYS = [
    'base_url',
    'client_id',
    'client_secret',
    'tpl_key',
    'user_login_id',
    'user_agent',
    'customer_id',
    'facility_id',
    'start_date'
]

def do_discover():

    LOGGER.info('Starting discover')
    catalog = discover()
    json.dump(catalog.to_dict(), sys.stdout, indent=2)
    LOGGER.info('Finished discover')


@singer.utils.handle_top_exception(LOGGER)
def main():

    parsed_args = singer.utils.parse_args(REQUIRED_CONFIG_KEYS)

    with TPLClient(
        base_url=parsed_args.config['base_url'],
        client_id=parsed_args.config['client_id'],
        client_secret=parsed_args.config['client_secret'],
        tpl_key=parsed_args.config['tpl_key'],
        user_login_id=parsed_args.config['user_login_id'],
        user_agent=parsed_args.config['user_agent']) as client:

        if parsed_args.state:
            state = parsed_args.state
        else:
            state = {}

        if parsed_args.discover:
            do_discover()
        elif parsed_args.catalog:
            sync(
                client=client,
                config=parsed_args.config,
                catalog=parsed_args.catalog,
                state=state,
                start_date=parsed_args.config['start_date']
                )

if __name__ == '__main__':
    main()
