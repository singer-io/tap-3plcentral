import io
import json
import runpy
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import tap_3plcentral
from tap_3plcentral.client import TPLClient, TPLAPIError
from tap_3plcentral.discover import _get_probe_resource_path
from tap_3plcentral.sync import process_records, sync_endpoint, write_record, sync
from tap_3plcentral.transform import denest_embedded_readonly_nodes


class TestMainCoverage(unittest.TestCase):
    @patch("tap_3plcentral.discover")
    def test_do_discover_writes_catalog(self, mock_discover):
        catalog = MagicMock()
        catalog.to_dict.return_value = {"streams": []}
        mock_discover.return_value = catalog

        with patch("sys.stdout", new=io.StringIO()) as stdout:
            tap_3plcentral.do_discover(MagicMock(), {"facility_id": "1"})
            payload = json.loads(stdout.getvalue())

        self.assertEqual(payload, {"streams": []})

    @patch("tap_3plcentral.sync")
    @patch("tap_3plcentral.do_discover")
    @patch("tap_3plcentral.TPLClient")
    @patch("tap_3plcentral.singer.utils.parse_args")
    def test_main_sync_path(self, mock_parse, mock_tpl_client, _mock_discover, mock_sync):
        parsed = MagicMock()
        parsed.discover = False
        parsed.catalog = MagicMock()
        parsed.state = {"bookmarks": {}}
        parsed.config = {
            "base_url": "https://secure-wms.com",
            "client_id": "id",
            "client_secret": "sec",
            "tpl_key": "tpl",
            "user_login_id": "1",
            "user_agent": "ua",
            "customer_id": "50",
            "facility_id": "1",
            "start_date": "2020-01-01T00:00:00Z",
        }
        mock_parse.return_value = parsed
        mock_client = MagicMock()
        mock_tpl_client.return_value.__enter__.return_value = mock_client

        tap_3plcentral.main()

        mock_sync.assert_called_once()

    @patch("tap_3plcentral.sync")
    @patch("tap_3plcentral.do_discover")
    @patch("tap_3plcentral.TPLClient")
    @patch("tap_3plcentral.singer.utils.parse_args")
    def test_main_discover_path(self, mock_parse, mock_tpl_client, mock_discover, mock_sync):
        parsed = MagicMock()
        parsed.discover = True
        parsed.catalog = None
        parsed.state = {}
        parsed.config = {
            "base_url": "https://secure-wms.com",
            "client_id": "id",
            "client_secret": "sec",
            "tpl_key": "tpl",
            "user_login_id": "1",
            "user_agent": "ua",
            "customer_id": "50",
            "facility_id": "1",
            "start_date": "2020-01-01T00:00:00Z",
        }
        mock_parse.return_value = parsed
        mock_client = MagicMock()
        mock_tpl_client.return_value.__enter__.return_value = mock_client

        tap_3plcentral.main()

        mock_discover.assert_called_once_with(mock_client, parsed.config)
        mock_sync.assert_not_called()

    @patch("singer.utils.parse_args")
    @patch("tap_3plcentral.client.TPLClient")
    def test_main_dunder_exec_path(self, mock_tpl_client, mock_parse):
        parsed = MagicMock()
        parsed.discover = False
        parsed.catalog = None
        parsed.state = {}
        parsed.config = {
            "base_url": "https://secure-wms.com",
            "client_id": "id",
            "client_secret": "sec",
            "tpl_key": "tpl",
            "user_login_id": "1",
            "user_agent": "ua",
            "customer_id": "50",
            "facility_id": "1",
            "start_date": "2020-01-01T00:00:00Z",
        }
        mock_parse.return_value = parsed
        mock_tpl_client.return_value.__enter__.return_value = MagicMock()

        init_file = Path(__file__).resolve().parents[2] / "tap_3plcentral" / "__init__.py"
        runpy.run_path(str(init_file), run_name="__main__")


class TestClientCoverage(unittest.TestCase):
    @patch("tap_3plcentral.client.TPLClient.post")
    def test_get_access_token_request(self, mock_post):
        mock_post.return_value = {"token_type": "Bearer", "access_token": "x"}
        client = TPLClient(
            base_url="https://secure-wms.com",
            client_id="cid",
            client_secret="csec",
            tpl_key="tpl",
            user_login_id="1",
            user_agent="ua",
            session=MagicMock(),
        )

        token = client._get_access_token()
        self.assertEqual(token["access_token"], "x")
        mock_post.assert_called_once()


class TestDiscoverCoverage(unittest.TestCase):
    def test_probe_path_locations_without_facility_id(self):
        self.assertEqual(_get_probe_resource_path("locations", facility_id=None), "locations")


class TestTransformCoverage(unittest.TestCase):
    def test_denest_embedded_item_branch(self):
        payload = {
            "ResourceList": [
                {
                    "_embedded": {"item": {"id": 99}},
                    "ReadOnly": {"created": "2024-01-01"},
                }
            ]
        }
        result = denest_embedded_readonly_nodes(payload, "ResourceList")
        record = result["ResourceList"][0]
        self.assertEqual(record["item"], {"id": 99})
        self.assertNotIn("_embedded", record)
        self.assertEqual(record["created"], "2024-01-01")


class TestSyncCoverage(unittest.TestCase):
    def _catalog_for_streams(self, selected_stream_ids=None):
        if selected_stream_ids is None:
            selected_stream_ids = []

        stream_obj = MagicMock()
        stream_obj.schema.to_dict.return_value = {
            "type": "object",
            "properties": {
                "id": {"type": ["null", "integer"]},
                "last_modified_date": {"type": ["null", "string"]},
                "order_id": {"type": ["null", "integer"]},
            },
        }
        stream_obj.key_properties = ["id"]
        stream_obj.metadata = [{"breadcrumb": (), "metadata": {"selected": True}}]

        catalog = MagicMock()
        catalog.get_stream.return_value = stream_obj
        catalog.streams = []
        for sid in selected_stream_ids:
            s = MagicMock()
            s.tap_stream_id = sid
            s.metadata = [{"breadcrumb": (), "metadata": {"selected": True}}]
            catalog.streams.append(s)
        return catalog

    @patch("tap_3plcentral.sync.singer.write_record", side_effect=OSError("write failed"))
    def test_write_record_oserror(self, _mock_write):
        with self.assertRaises(OSError):
            write_record("orders", {"id": 1}, time_extracted="x")

    @patch("tap_3plcentral.sync.write_record")
    def test_process_records_datetime_and_integer_branches(self, mock_write):
        catalog = self._catalog_for_streams()

        records_dt = [{"id": 1, "last_modified_date": "2020-01-02T00:00:00Z"}]
        max_bm_dt, count_dt = process_records(
            catalog=catalog,
            stream_name="orders",
            records=records_dt,
            time_extracted="x",
            bookmark_field="last_modified_date",
            bookmark_type="datetime",
            max_bookmark_value="2020-01-01T00:00:00Z",
            last_datetime="2020-01-01T00:00:00Z",
        )
        self.assertEqual(count_dt, 1)
        self.assertEqual(max_bm_dt, "2020-01-02T00:00:00Z")

        records_int = [{"id": 2, "order_id": 10}]
        max_bm_int, count_int = process_records(
            catalog=catalog,
            stream_name="orders",
            records=records_int,
            time_extracted="x",
            bookmark_field="order_id",
            bookmark_type="integer",
            max_bookmark_value=0,
            last_integer=5,
        )
        self.assertEqual(count_int, 1)
        self.assertEqual(max_bm_int, 10)
        self.assertGreaterEqual(mock_write.call_count, 2)

    @patch("tap_3plcentral.sync.write_schema")
    @patch("tap_3plcentral.sync.write_bookmark")
    @patch("tap_3plcentral.sync.process_records")
    @patch("tap_3plcentral.sync.transform_json")
    def test_sync_endpoint_covers_children_and_pagination(self, mock_transform, mock_process, mock_write_bookmark, _mock_write_schema):
        catalog = self._catalog_for_streams(selected_stream_ids=["sku_items"])
        client = MagicMock()
        state = {"bookmarks": {}}

        parent_response = {
            "ResourceList": [{"id": 7}],
            "TotalResults": 1,
        }
        child_empty_response = []
        client.get.side_effect = [parent_response, child_empty_response]

        mock_transform.return_value = {"resource_list": [{"id": 7}]}
        mock_process.return_value = ("2020-01-02T00:00:00Z", 1)

        endpoint_config = {
            "children": {
                "sku_items": {
                    "path": "customers/{}/items",
                    "params": {"pgsiz": 100, "rql": "status==active"},
                    "data_key": "ResourceList",
                    "bookmark_query_field": "ReadOnly.lastModifiedDate",
                    "bookmark_field": "last_modified_date",
                    "bookmark_type": "datetime",
                    "id_fields": ["id"],
                    "parent": "customer",
                }
            }
        }

        result = sync_endpoint(
            client=client,
            catalog=catalog,
            state=state,
            start_date="2020-01-01T00:00:00Z",
            stream_name="customers",
            path="customers",
            endpoint_config=endpoint_config,
            data_key="ResourceList",
            static_params={"pgsiz": 100},
            bookmark_query_field="ReadOnly.lastModifiedDate",
            bookmark_field="last_modified_date",
            bookmark_type="datetime",
            id_fields=["id"],
        )

        self.assertEqual(result, 1)
        mock_write_bookmark.assert_called()

    @patch("tap_3plcentral.sync.write_schema")
    @patch("tap_3plcentral.sync.process_records", return_value=(5, 1))
    @patch("tap_3plcentral.sync.transform_json")
    def test_sync_endpoint_integer_and_data_key_none(self, mock_transform, _mock_process, _mock_write_schema):
        catalog = self._catalog_for_streams()
        client = MagicMock()
        state = {"bookmarks": {"inventory": {"id": 1}}}
        client.get.return_value = {"ResourceList": [{"id": 9}], "TotalResults": 1}
        mock_transform.return_value = {"resource_list": {"id": 9}}

        total = sync_endpoint(
            client=client,
            catalog=catalog,
            state=state,
            start_date="2020-01-01T00:00:00Z",
            stream_name="inventory",
            path="inventory",
            endpoint_config={},
            data_key=None,
            static_params={"pgsiz": 50, "rql": "x=eq=1"},
            bookmark_query_field="id",
            bookmark_field="id",
            bookmark_type="integer",
            id_fields=["id"],
        )

        self.assertEqual(total, 1)

    @patch("tap_3plcentral.sync.write_schema")
    @patch("tap_3plcentral.sync.process_records", return_value=(10, 2))
    @patch("tap_3plcentral.sync.transform_json")
    def test_sync_endpoint_integer_rql_without_pgsiz_and_no_totalresults(self, mock_transform, _mock_process, _mock_write_schema):
        catalog = self._catalog_for_streams()
        client = MagicMock()
        state = {"bookmarks": {"orders": {"order_id": 5}}}
        client.get.return_value = {"ResourceList": [{"id": 1, "order_id": 10}]}
        mock_transform.return_value = {"resource_list": [{"id": 1, "order_id": 10}]}

        total = sync_endpoint(
            client=client,
            catalog=catalog,
            state=state,
            start_date="2020-01-01T00:00:00Z",
            stream_name="orders",
            path="orders",
            endpoint_config={},
            data_key="ResourceList",
            static_params={},
            bookmark_query_field="order_id",
            bookmark_field="order_id",
            bookmark_type="integer",
            id_fields=["id"],
        )

        self.assertEqual(total, 2)
        querystring = client.get.call_args.kwargs["querystring"]
        self.assertIn("rql=order_id=ge=5", querystring)

    @patch("tap_3plcentral.sync.write_schema")
    @patch("tap_3plcentral.sync.transform_json")
    def test_sync_endpoint_breaks_on_empty_transformed_data(self, mock_transform, _mock_write_schema):
        catalog = self._catalog_for_streams()
        client = MagicMock()
        state = {"bookmarks": {}}
        client.get.return_value = {"ResourceList": [{"id": 1}]}
        mock_transform.return_value = {"resource_list": []}

        total = sync_endpoint(
            client=client,
            catalog=catalog,
            state=state,
            start_date="2020-01-01T00:00:00Z",
            stream_name="orders",
            path="orders",
            endpoint_config={},
            data_key="ResourceList",
            static_params={"pgsiz": 100},
            bookmark_query_field=None,
            bookmark_field=None,
            bookmark_type=None,
            id_fields=["id"],
        )

        self.assertEqual(total, 0)

    @patch("tap_3plcentral.sync.sync_endpoint", return_value=2)
    @patch("tap_3plcentral.sync.update_currently_syncing")
    @patch("tap_3plcentral.sync.get_selected_streams", return_value=["locations"])
    @patch("tap_3plcentral.sync.singer.get_currently_syncing", return_value="locations")
    def test_sync_locations_path(self, _mock_cur, _mock_sel, mock_update, mock_sync_endpoint):
        config = {
            "start_date": "2020-01-01T00:00:00Z",
            "customer_id": "50",
            "facility_id": "777",
        }
        sync(MagicMock(), config, self._catalog_for_streams(), {}, "2020-01-01T00:00:00Z")
        called_path = mock_sync_endpoint.call_args.kwargs["path"]
        self.assertEqual(called_path, "inventory/facilities/777/locations")
        self.assertEqual(mock_update.call_count, 2)
