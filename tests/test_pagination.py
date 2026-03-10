from base import ThreePLCentralBaseTest
from tap_tester.base_suite_tests.pagination_test import PaginationTest


class ThreePLCentralPaginationTest(PaginationTest, ThreePLCentralBaseTest):
    """
    Ensure tap can replicate multiple pages of data for streams that use
    pagination.
    """

    @staticmethod
    def name():
        return "tap_tester_3plcentral_pagination_test"

    def streams_to_test(self):
        streams_to_exclude = set()
        return self.expected_stream_names().difference(streams_to_exclude)

    def get_properties(self, original: bool = True):
        """Configuration with reduced page_size to test pagination logic."""
        return {
            "base_url": "https://secure-wms.com",
            "user_login_id": "1",
            "user_agent": "tap-3plcentral <test@test.com>",
            "customer_id": "50",
            "facility_id": "1",
            "start_date": "2025-09-01T00:00:00Z",
        }

    def expected_page_size(self, stream):
        """
        Return the expected page size for pagination testing.

        Each stream in tap-3plcentral has its own page size configured
        via the pgsiz parameter in the endpoints configuration.
        """
        page_sizes = {
            "inventory": 200,
            "locations": 200,
            "stock_summaries": 200,
            "customers": 100,
            "sku_items": 100,
            "stock_details": 100,
            "orders": 200,
        }
        return page_sizes.get(stream, 100)
