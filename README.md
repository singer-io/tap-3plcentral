# tap-tplcentral

This is a [Singer](https://singer.io) tap that produces JSON-formatted data
following the [Singer
spec](https://github.com/singer-io/getting-started/blob/master/SPEC.md).

This tap:

- Pulls raw data from the [3PLCentral REST API](http://api.3plcentral.com/rels/)
- Extracts the following resources:
  - [Customers](http://api.3plcentral.com/rels/customers/customers)
    - [Customer Items (SKUs)](http://api.3plcentral.com/rels/customers/items)
    - [Customer Stock Details](http://api.3plcentral.com/rels/inventory/stockdetails)
  - [Inventory](http://api.3plcentral.com/rels/inventory/inventory)
  - [Orders](http://api.3plcentral.com/rels/orders/orders)
    - [Order Items](http://api.3plcentral.com/rels/orders/items)
    - [Order Packages](http://api.3plcentral.com/rels/orders/packages)
  - [Stock Summaries](http://api.3plcentral.com/rels/inventory/stocksummaries)
- Outputs the schema for each resource
- Incrementally pulls data based on the input state

## Quick Start

1. Install

    Clone this repository, and then install using setup.py. We recommend using a virtualenv:

    ```bash
    > virtualenv -p python3 venv
    > source venv/bin/activate
    > python setup.py install
    OR
    > cd .../tap-tplcentral
    > pip install .
    ```
2. Dependent libraries
    The following dependent libraries were installed.
    ```bash
    > pip install singer-python
    > pip install singer-tools
    > pip install target-stitch
    > pip install target-json
    
    ```
    - [singer-tools](https://github.com/singer-io/singer-tools)
    - [target-stitch](https://github.com/singer-io/target-stitch)
3. Create your tap's config file which should look like the following:

    ```json
    {
        "start_date": "2019-01-01T00:00:00Z",
        "client_id": "OAUTH_CLIENT_ID",
        "client_secret": "OAUTH_CLIENT_SECRET",
        "tpl_key": "WH_SPECIFIC_TPL_KEY",
        "user_login_id": "USER_INTEGER_ID",
        "user_agent": "tap-tplcentral <my.email@domain.com>",
        "base_url": "http://secure-wms.com",
        "customer_id": "CUSTOMER_INTEGER_ID",
        "facility_id": "FACILITY_INTEGER_ID"
    }
    ```

4. Run the Tap in Discovery Mode
    This creates a catalog.json for selecting objects/fields to integrate:
    ```bash
    tap-tplcentral --config config.json --discover > catalog.json
    ```
   See the Singer docs on discovery mode
   [here](https://github.com/singer-io/getting-started/blob/master/docs/DISCOVERY_MODE.md#discovery-mode).

5. Run the Tap in Sync Mode (with catalog) and [write out to state file](https://github.com/singer-io/getting-started/blob/master/docs/RUNNING_AND_DEVELOPING.md#running-a-singer-tap-with-a-singer-target)

    For Sync mode:
    ```bash
    > tap-tplcentral --config tap_config.json --catalog catalog.json >> state.json
    > tail -1 state.json > state.json.tmp && mv state.json.tmp state.json
    ```
    To load to json files to verify outputs:
    ```bash
    > tap-tplcentral --config tap_config.json --catalog catalog.json | target-json >> state.json
    > tail -1 state.json > state.json.tmp && mv state.json.tmp state.json
    ```
    To pseudo-load to [Stitch Import API](https://github.com/singer-io/target-stitch) with dry run:
    ```bash
    > tap-tplcentral --config tap_config.json --catalog catalog.json | target-stitch --config target_config.json --dry-run >> state.json
    > tail -1 state.json > state.json.tmp && mv state.json.tmp state.json
    ```

6. Test the Tap
    
    While developing the tplcentral tap, the following utilities were run in accordance with Singer.io best practices:
    Pylint to improve [code quality](https://github.com/singer-io/getting-started/blob/master/docs/BEST_PRACTICES.md#code-quality):
    ```bash
    > pylint tap_tplcentral -d missing-docstring -d logging-format-interpolation -d too-many-locals -d too-many-arguments
    ```

    To [check the tap](https://github.com/singer-io/singer-tools#singer-check-tap) and verify working:
    ```bash
    > tap-tplcentral --config tap_config.json --catalog catalog.json | singer-check-tap >> state.json
    > tail -1 state.json > state.json.tmp && mv state.json.tmp state.json
    ```

---

Copyright &copy; 2019 Stitch
