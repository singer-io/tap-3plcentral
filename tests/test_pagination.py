"""Mock integration test: pagination — tap correctly fetches all pages."""
import unittest
from unittest.mock import patch, MagicMock

from tap_3plcentral.sync import sync

try:
    from .base import ThreePLCentralMockBaseTest
except ImportError:
    from base import ThreePLCentralMockBaseTest


class PaginationIntegrationTest(ThreePLCentralMockBaseTest, unittest.TestCase):

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_pagination_fetches_all_pages(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """When TotalResults > pgsiz, the tap should paginate and fetch
        all records across multiple pages."""
        catalog = self._make_selected_catalog(stream_names={"inventory"})

        # The inventory endpoint uses pgsiz=200 by default.
        # We create 500 records so TotalResults=500 > pgsiz=200,
        # forcing the tap to make 3 GET calls (pages of 200, 200, 100).
        total = 500
        all_records = [
            {"ReceiveItemId": i, "ReceivedDate": "2025-06-01T00:00:00"}
            for i in range(1, total + 1)
        ]

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            # Parse pgnum and pgsiz from querystring
            pgnum = 1
            pgsiz = 200
            if querystring:
                for part in querystring.split("&"):
                    if part.startswith("pgnum="):
                        pgnum = int(part.split("=")[1])
                    if part.startswith("pgsiz="):
                        pgsiz = int(part.split("=")[1])
            start = (pgnum - 1) * pgsiz
            end = start + pgsiz
            page = all_records[start:end]
            return {
                "TotalResults": total,
                "ResourceList": page,
            }

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)
        state = {}

        sync(client, config, catalog, state, config["start_date"])

        # All 500 records should be written
        inventory_records = [
            call_args[0][1]
            for call_args in mock_write_record.call_args_list
            if call_args[0][0] == "inventory"
        ]
        self.assertEqual(len(inventory_records), total)

        # Verify the client made multiple GET calls (pagination)
        self.assertGreater(client.get.call_count, 1)

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_single_page_no_extra_requests(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """When all records fit in one page, only one GET should be made."""
        catalog = self._make_selected_catalog(stream_names={"inventory"})

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            return {
                "TotalResults": 2,
                "ResourceList": [
                    {"ReceiveItemId": 1, "ReceivedDate": "2025-06-01T00:00:00"},
                    {"ReceiveItemId": 2, "ReceivedDate": "2025-06-02T00:00:00"},
                ],
            }

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)
        state = {}

        sync(client, config, catalog, state, config["start_date"])

        # Only 1 GET for inventory (fits in one page with pgsiz=200)
        self.assertEqual(client.get.call_count, 1)
        self.assertEqual(mock_write_record.call_count, 2)
