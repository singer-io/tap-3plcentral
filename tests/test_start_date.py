from base import ThreePLCentralBaseTest
from tap_tester.base_suite_tests.start_date_test import StartDateTest


class ThreePLCentralStartDateTest(StartDateTest, ThreePLCentralBaseTest):
    """Instantiate start date according to the desired data set and run the
    test."""

    @staticmethod
    def name():
        return "tap_tester_3plcentral_start_date_test"

    def streams_to_test(self):
        # Only incremental streams that obey start_date
        streams_to_exclude = {
            # Full table replication streams (start_date not applicable)
            "customers",
            "stock_details",
            "stock_summaries",
            "locations",
            "inventory",
        }
        return self.expected_stream_names().difference(streams_to_exclude)

    @property
    def start_date_1(self):
        return "2025-11-01T00:00:00Z"

    @property
    def start_date_2(self):
        return "2026-01-01T00:00:00Z"
