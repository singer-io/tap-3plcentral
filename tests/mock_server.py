#!/usr/bin/env python3
"""
Mock 3PLCentral API server for tap-tester integration tests.

Runs a local HTTP server that mimics the 3PLCentral REST API,
returning mock data for all supported streams. Supports pagination
and RQL date filtering for incremental streams.

Usage:
    python tests/mock_server.py [--port PORT]
"""

import json
import re
import sys
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

DEFAULT_PORT = 8765

# ---------------------------------------------------------------------------
# Mock data generators
# ---------------------------------------------------------------------------

def _dt(year, month, day, hour=0):
    return f"{year}-{month:02d}-{day:02d}T{hour:02d}:00:00Z"


def generate_customers(count=105):
    """Generate mock customer records in 3PLCentral API format (CamelCase, ReadOnly wrapper)."""
    records = []
    base = datetime(2024, 1, 1)
    for i in range(1, count + 1):
        d = base + timedelta(days=i)
        records.append({
            "ReadOnly": {
                "CustomerId": i,
                "CreationDate": d.strftime("%Y-%m-%dT%H:%M:%S"),
                "Deactivated": False,
            },
            "CompanyInfo": {
                "ContactId": i,
                "CompanyName": f"Company {i}",
                "Name": f"Contact {i}",
                "Title": "Manager",
                "Address1": f"{i} Main St",
                "Address2": "",
                "City": "Testville",
                "State": "CA",
                "Zip": "90210",
                "Country": "US",
                "PhoneNumber": f"555-{i:04d}",
                "Fax": "",
                "EmailAddress": f"contact{i}@test.com",
                "Dept": "Ops",
                "Code": f"C{i:04d}",
                "AddressStatus": 0,
            },
            "PrimaryContact": {
                "ContactId": i + 1000,
                "CompanyName": f"Company {i}",
                "Name": f"Primary {i}",
                "Title": "Director",
                "Address1": f"{i} Main St",
                "Address2": "",
                "City": "Testville",
                "State": "CA",
                "Zip": "90210",
                "Country": "US",
                "PhoneNumber": f"555-{i:04d}",
                "Fax": "",
                "EmailAddress": f"primary{i}@test.com",
                "Dept": "Sales",
                "Code": f"P{i:04d}",
                "AddressStatus": 0,
            },
            "OtherContacts": [],
            "Website": f"https://company{i}.example.com",
            "ExternalId": f"EXT-{i:04d}",
            "Groups": [f"group-{(i % 3) + 1}"],
            "Facilities": [{"Name": "Main Warehouse", "Id": 1}],
            "PrimaryFacilityIdentifier": {"Name": "Main Warehouse", "Id": 1},
            "Options": {
                "Alerts": {
                    "ExpirationNotificationThreshold": 30,
                    "NotifyShipTo": False,
                    "FromEmailAddress": "",
                },
                "Storage": {
                    "FuelSurcharge": 0.0,
                    "SetInvoiceDateToXactionConfirmDate": False,
                    "AccountingCustomerName": f"Company {i}",
                    "AutoFillChargesOnConfirm": True,
                },
                "Edi": {
                    "CustInterchangeId": "",
                    "CustInterchangeIdQual": "",
                    "ThreeplInterchangeId": "",
                    "ThreeplInterchangeIdQual": "",
                    "TradingPartnerId": "",
                },
            },
        })
    return records


def generate_sku_items(customer_id, count=3):
    """Generate mock SKU item records for a given customer."""
    records = []
    # Spread dates across test-relevant range
    dates = [
        _dt(2025, 6, 15, 10),   # before bookmark (2025-09-01)
        _dt(2025, 10, 20, 14),  # between start_date_1 (2025-11-01) and bookmark
        _dt(2025, 12, 5, 8),    # between start_date_1 and start_date_2 (2026-01-01)
        _dt(2026, 2, 10, 16),   # after start_date_2
    ]
    for j in range(count):
        item_id = customer_id * 1000 + j + 1
        dt_val = dates[j % len(dates)]
        records.append({
            "ReadOnly": {
                "CustomerIdentifier": {
                    "ExternalId": f"EXT-{customer_id:04d}",
                    "Name": f"Company {customer_id}",
                    "Id": customer_id,
                },
                "ItemId": item_id,
                "CreationDate": _dt(2024, 6, 1),
                "LastModifiedDate": dt_val,
                "Deactivated": False,
                "LastPriceChange": _dt(2025, 1, 1),
            },
            "ItemId": item_id,
            "Sku": f"SKU-{item_id}",
            "Upc": f"UPC-{item_id}",
            "Description": f"Test Item {item_id}",
            "Description2": "",
            "InventoryCategory": "General",
            "ClassificationIdentifier": {"Name": "Standard", "Id": 1},
            "Nmfc": "",
            "Cost": round(10.0 + j * 5.5, 2),
            "Price": round(20.0 + j * 8.0, 2),
            "Temperature": 0.0,
            "AccountRef": "",
            "CountryOfManufacture": "US",
            "HarmonizedCode": "",
            "QualifierRenamers": [],
            "Kit": None,
            "Options": {
                "InventoryUnit": {
                    "UnitIdentifier": {"Name": "Each", "Id": 1},
                    "MinimumStock": 0.0,
                    "MaximumStock": 0.0,
                    "ReorderQuantity": 0.0,
                    "InventoryMethod": 0,
                },
                "SecondaryUnit": None,
                "PackageUnit": None,
                "TrackBys": {
                    "TrackLotNumber": 0,
                    "TrackSerialNumber": 0,
                    "TrackExpirationDate": 0,
                    "TrackCost": 0,
                },
                "Movement": None,
            },
            "SavedElements": [],
            "Item": [{"Qualifier": f"Q-{item_id}"}],
        })
    return records


def generate_stock_details(count=105):
    """Generate mock stock detail records."""
    records = []
    for i in range(1, count + 1):
        records.append({
            "ReceiveItemId": i,
            "ItemIdentifier": {"Sku": f"SKU-{i}", "Id": i},
            "Description": f"Stock Detail Item {i}",
            "Qualifier": "",
            "Received": 100.0 + i,
            "Available": 80.0 + i,
            "IsOnHold": False,
            "Quarantined": False,
            "OnHand": 90.0 + i,
            "LotNumber": f"LOT-{i:04d}",
            "SerialNumber": f"SN-{i:06d}",
            "ExpirationDate": _dt(2027, 12, 31),
            "Cost": round(5.0 + i * 0.5, 2),
            "SupplierIdentifier": {"Name": f"Supplier {(i % 5) + 1}", "Id": (i % 5) + 1},
            "LocationIdentifier": {
                "NameKey": {
                    "FacilityIdentifier": {"Name": "Main Warehouse", "Id": 1},
                    "Name": f"Loc-{(i % 10) + 1}",
                },
                "Id": (i % 10) + 1,
            },
            "PalletIdentifier": {
                "NameKey": {
                    "FacilityIdentifier": {"Name": "Main Warehouse", "Id": 1},
                    "Name": f"Pallet-{(i % 5) + 1}",
                },
                "Id": (i % 5) + 1,
            },
            "InventoryUnitOfMeasureIdentifier": {"Name": "Each", "Id": 1},
            "ReceiverId": i + 100,
            "ReceivedDate": _dt(2025, 6, (i % 28) + 1),
            "ReferenceNum": f"REF-{i:04d}",
            "PoNum": f"PO-{i:04d}",
            "TrailerNumber": f"TRL-{i:03d}",
            "SavedElements": [],
        })
    return records


def generate_stock_summaries(count=205):
    """Generate mock stock summary records."""
    records = []
    for i in range(1, count + 1):
        records.append({
            "ItemIdentifier": {"Sku": f"SKU-{i}", "Id": i},
            "Qualifier": "",
            "TotalReceived": 100.0 + i,
            "Allocated": float(i % 20),
            "Available": 80.0 + i,
            "OnHold": float(i % 10),
            "OnHand": 90.0 + i,
            "FacilityId": 1,
        })
    return records


def generate_locations(facility_id, count=205):
    """Generate mock location records for a facility."""
    records = []
    for i in range(1, count + 1):
        records.append({
            "LocationIdentifier": {
                "NameKey": {
                    "FacilityIdentifier": {"Name": "Main Warehouse", "Id": facility_id},
                    "Name": f"LOC-{i:04d}",
                },
                "Id": i,
            },
            "Description": f"Location {i}",
            "LocationTypeIdentifier": {"Name": "Standard", "Id": 1},
            "ItemTraits": {
                "ItemIdentifier": {"Sku": f"SKU-{(i % 50) + 1}", "Id": (i % 50) + 1},
                "Qualifier": "",
                "LotNumber": "",
                "SerialNumber": "",
                "ExpirationDate": None,
                "PalletIdentifier": None,
            },
            "CustomerIdentifier": {"ExternalId": "EXT-0001", "Name": "Company 1", "Id": 1},
            "OnHand": float(i * 10),
        })
    return records


def generate_inventory(count=205):
    """Generate mock inventory records."""
    records = []
    base = datetime(2025, 1, 1)
    for i in range(1, count + 1):
        d = base + timedelta(days=i % 365)
        records.append({
            "ReceiverId": i + 500,
            "ReceivedDate": d.strftime("%Y-%m-%dT%H:%M:%S"),
            "ReceiveItemId": i,
            "CustomerIdentifier": {
                "ExternalId": f"EXT-{(i % 5) + 1:04d}",
                "Name": f"Company {(i % 5) + 1}",
                "Id": (i % 5) + 1,
            },
            "FacilityIdentifier": {"Name": "Main Warehouse", "Id": 1},
            "ItemIdentifier": {"Sku": f"SKU-{i}", "Id": i},
            "ItemDescription": f"Inventory Item {i}",
            "Qualifier": "",
            "InventoryUnitOfMeasureIdentifier": {"Name": "Each", "Id": 1},
            "SecondaryUnitOfMeasureIdentifier": None,
            "InventoryUnitsPerSecondaryUnity": 0.0,
            "ReceiveQty": 100.0 + i,
            "OnHandQty": 90.0 + i,
            "AvailableQty": 80.0 + i,
            "OnHoldQty": 0.0,
            "SecondaryReceivedQty": 0.0,
            "SecondaryOnHandQty": 0.0,
            "SecondaryAvailableQty": 0.0,
            "SecondaryOnHoldQty": 0.0,
            "WeightImperial": 1.0 + i * 0.1,
            "WeightImperialOnHand": 0.9 + i * 0.1,
            "WeightImperialAvailable": 0.8 + i * 0.1,
            "WeightMetric": 0.5 + i * 0.05,
            "WeightMetricOnHand": 0.45 + i * 0.05,
            "WeightMetricAvailable": 0.4 + i * 0.05,
            "LotNumber": f"LOT-{i:04d}",
            "SerialNumber": f"SN-{i:06d}",
            "ExpirationDate": _dt(2027, 12, 31),
            "Cost": round(5.0 + i * 0.25, 2),
            "SupplierIdentifier": {"Name": f"Supplier {(i % 5) + 1}", "Id": (i % 5) + 1},
            "LocationIdentifier": {
                "NameKey": {
                    "FacilityIdentifier": {"Name": "Main Warehouse", "Id": 1},
                    "Name": f"Loc-{(i % 10) + 1}",
                },
                "Id": (i % 10) + 1,
            },
            "PalletIdentifier": {
                "NameKey": {
                    "FacilityIdentifier": {"Name": "Main Warehouse", "Id": 1},
                    "Name": f"Pallet-{(i % 5) + 1}",
                },
                "Id": (i % 5) + 1,
            },
            "OnHold": False,
            "OnHoldReason": None,
            "OnHoldDate": None,
            "OnHoldUserIdentifier": None,
            "Quarantined": False,
        })
    return records


def generate_orders(count=205):
    """Generate mock order records with dates spanning test-relevant ranges."""
    records = []
    # Distribute dates across the range 2025-01-01 to 2026-03-01
    base = datetime(2025, 1, 1)
    total_days = (datetime(2026, 3, 1) - base).days
    for i in range(1, count + 1):
        d = base + timedelta(days=int((i - 1) * total_days / count))
        dt_str = d.strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append({
            "ReadOnly": {
                "OrderId": i,
                "AsnCandidate": 0,
                "RouteCandidate": 0,
                "FullyAllocated": True,
                "ExportModuleIds": "",
                "DeferNotification": False,
                "IsClosed": i % 5 == 0,
                "ProcessDate": dt_str,
                "PickDoneDate": dt_str,
                "PickTicketPrintDate": None,
                "PackDoneDate": dt_str,
                "LabelsExported": False,
                "InvoiceExportedDate": None,
                "InvoiceDeliveredDate": None,
                "LoadedState": 0,
                "LoadOutDoneDate": None,
                "ReallocatedAfterPickTicketDate": None,
                "RouteSent": False,
                "AsnSentDate": None,
                "AsnSent": False,
                "PkgsExported": False,
                "BatchIdentifier": {
                    "NameKey": {
                        "CustomerIdentifier": {
                            "ExternalId": f"EXT-{(i % 5) + 1:04d}",
                            "Name": f"Company {(i % 5) + 1}",
                            "Id": (i % 5) + 1,
                        },
                        "Name": f"Batch-{i}",
                    },
                    "Id": i,
                },
                "Packages": [],
                "OutboundSerialNumbers": [],
                "ParcelLabelType": 0,
                "CustomerIdentifier": {
                    "ExternalId": f"EXT-{(i % 5) + 1:04d}",
                    "Name": f"Company {(i % 5) + 1}",
                    "Id": (i % 5) + 1,
                },
                "FacilityIdentifier": {"Name": "Main Warehouse", "Id": 1},
                "WarehouseTransactionSourceType": 0,
                "TransactionEntryType": 0,
                "ImportChannelIdentifier": {"Name": "", "Id": 0},
                "CreationDate": dt_str,
                "LastModifiedDate": dt_str,
            },
            "CustomerIdentifier": {
                "ExternalId": f"EXT-{(i % 5) + 1:04d}",
                "Name": f"Company {(i % 5) + 1}",
                "Id": (i % 5) + 1,
            },
            "FacilityIdentifier": {"Name": "Main Warehouse", "Id": 1},
            "ReferenceNum": f"ORD-{i:05d}",
            "PoNum": f"PO-{i:05d}",
            "Retailer": None,
            "BillingCode": "Prepaid",
            "RoutingInfo": {
                "Carrier": f"Carrier-{(i % 3) + 1}",
                "Mode": "Ground",
                "Account": "",
                "LoadNumber": "",
            },
            "ShipTo": {
                "ContactId": 0,
                "CompanyName": f"Ship To {i}",
                "Name": f"Recipient {i}",
                "Title": "",
                "Address1": f"{i} Ship St",
                "Address2": "",
                "City": "Destville",
                "State": "NY",
                "Zip": "10001",
                "Country": "US",
                "PhoneNumber": f"555-{i:04d}",
                "Fax": "",
                "EmailAddress": f"ship{i}@test.com",
                "Dept": "",
                "Code": "",
                "AddressStatus": 0,
            },
            "Status": 1,
            "Description": f"Order {i} description",
            "NumUnits": float(i * 2),
            "TotalWeight": float(i) * 1.5,
            "TotalVolume": float(i) * 0.5,
            "UpServiceOptionCharge": 0.0,
            "UpTransportationCharge": 0.0,
            "UpsIsResidential": 0.0,
            "AddFreightToCod": False,
            "AsnNumber": f"ASN-{i:05d}",
            "ExternalId": f"EXTORD-{i:05d}",
            "InvoiceNumber": f"INV-{i:05d}",
            "MasterBillingOfLadingId": f"MBOL-{i:05d}",
            "ShippingNotes": f"Ship notes for order {i}",
            "EarliestShipDate": dt_str,
            "ShipCancelDate": None,
            "RoutePickupDate": None,
            "ExportChannelIdentifier": {"Name": "", "Id": 0},
            "CreatedByIdentifier": {"Name": f"User {(i % 3) + 1}", "Id": (i % 3) + 1},
            "LastModifiedByIdentifier": {"Name": f"User {(i % 3) + 1}", "Id": (i % 3) + 1},
            "Unit2Identifier": {"Name": "Box", "Id": 1},
            "BillTo": {
                "ContactId": 0,
                "CompanyName": f"Bill To {i}",
                "Name": f"Payer {i}",
                "Title": "",
                "Address1": f"{i} Bill St",
                "Address2": "",
                "City": "Billville",
                "State": "TX",
                "Zip": "73301",
                "Country": "US",
                "PhoneNumber": "",
                "Fax": "",
                "EmailAddress": "",
                "Dept": "",
                "Code": "",
                "AddressStatus": 0,
            },
            "SoldTo": {
                "ContactId": 0,
                "CompanyName": f"Sold To {i}",
                "Name": f"Buyer {i}",
                "Title": "",
                "Address1": f"{i} Sold St",
                "Address2": "",
                "City": "Soldville",
                "State": "FL",
                "Zip": "33101",
                "Country": "US",
                "PhoneNumber": "",
                "Fax": "",
                "EmailAddress": "",
                "Dept": "",
                "Code": "",
                "AddressStatus": 0,
            },
            "Billing": {
                "FreightAccountNumber": "",
                "FreightBillingType": 0,
            },
            "FulfillInvInfo": {
                "FulfillInvShipmentId": 0,
                "FulfillInvPickticketId": 0,
            },
            "OrderItems": [],
            "SavedElements": [],
            "Notes": "",
        })
    return records


# ---------------------------------------------------------------------------
# Pre-generate all data at module load
# ---------------------------------------------------------------------------

ALL_CUSTOMERS = generate_customers(105)
ALL_STOCK_DETAILS = generate_stock_details(2)
ALL_STOCK_SUMMARIES = generate_stock_summaries(205)
ALL_INVENTORY = generate_inventory(205)
ALL_ORDERS = generate_orders(205)


# ---------------------------------------------------------------------------
# RQL date filter parsing
# ---------------------------------------------------------------------------

def parse_rql_date_filter(rql_string):
    """Parse RQL filter like 'ReadOnly.lastModifiedDate=ge=2025-09-01T00:00:00Z'
    and return (field_name, operator, datetime_value) or None."""
    if not rql_string:
        return None
    # Match patterns like: field=ge=value or field1;field=ge=value
    parts = rql_string.split(";")
    for part in parts:
        match = re.match(r"([\w.]+)=(ge|le|gt|lt)=(.+)", part)
        if match:
            return match.group(1), match.group(2), match.group(3)
    return None


def filter_by_rql(records, rql_string, date_field_path):
    """Filter records by RQL date filter.
    date_field_path is the path to the date field in each record,
    e.g., 'ReadOnly.LastModifiedDate'."""
    rql_filter = parse_rql_date_filter(rql_string)
    if rql_filter is None:
        return records

    _, op, filter_value = rql_filter

    def get_nested(record, path):
        parts = path.split(".")
        val = record
        for p in parts:
            if val is None:
                return None
            # Case-insensitive key lookup
            found = False
            for k in val:
                if k.lower() == p.lower():
                    val = val[k]
                    found = True
                    break
            if not found:
                return None
        return val

    filtered = []
    for rec in records:
        val = get_nested(rec, date_field_path)
        if val is None:
            filtered.append(rec)
            continue
        if op == "ge" and val >= filter_value:
            filtered.append(rec)
        elif op == "gt" and val > filter_value:
            filtered.append(rec)
        elif op == "le" and val <= filter_value:
            filtered.append(rec)
        elif op == "lt" and val < filter_value:
            filtered.append(rec)

    return filtered


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------

def paginate(records, pgnum, pgsiz):
    """Return a page of records."""
    start = (pgnum - 1) * pgsiz
    end = start + pgsiz
    return records[start:end]


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class MockAPIHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests mimicking the 3PLCentral API."""

    # Stateful counter for stock_details to generate unique receive_item_ids
    # across parent customer iterations.
    _stock_details_call_count = 0

    def log_message(self, fmt, *args):
        """Suppress default logging to stderr; use simple print instead."""
        print(f"[MockAPI] {fmt % args}")

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/hal+json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _parse_query(self, query_string):
        return parse_qs(query_string, keep_blank_values=True)

    def do_POST(self):
        parsed = urlparse(self.path)

        # Auth endpoint
        if parsed.path.rstrip("/") in ("/AuthServer/api/Token", "/authserver/api/token"):
            self._send_json({
                "token_type": "Bearer",
                "access_token": "mock_access_token_for_testing",
                "expires_in": 3600,
            })
            return

        self._send_json({"error": "Not Found"}, 404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.strip("/")
        params = self._parse_query(parsed.query)

        pgnum = int(params.get("pgnum", [1])[0])
        pgsiz = int(params.get("pgsiz", [100])[0])
        rql = params.get("rql", [None])[0]

        # --- customers ---
        if path == "customers":
            page = paginate(ALL_CUSTOMERS, pgnum, pgsiz)
            self._send_json({
                "TotalResults": len(ALL_CUSTOMERS),
                "ResourceList": page,
            })
            return

        # --- customers/{id}/items (sku_items) ---
        match = re.match(r"customers/(\d+)/items", path)
        if match:
            customer_id = int(match.group(1))
            all_items = generate_sku_items(customer_id, count=4)
            filtered = filter_by_rql(
                all_items, rql, "ReadOnly.LastModifiedDate"
            )
            page = paginate(filtered, pgnum, pgsiz)
            self._send_json({
                "TotalResults": len(filtered),
                "ResourceList": page,
            })
            return

        # --- inventory/stockdetails ---
        if path == "inventory/stockdetails":
            # Each call (from different parent customers) gets unique IDs
            call_num = MockAPIHandler._stock_details_call_count
            MockAPIHandler._stock_details_call_count += 1
            offset = call_num * len(ALL_STOCK_DETAILS)
            shifted = []
            for rec in ALL_STOCK_DETAILS:
                r = dict(rec)
                r["ReceiveItemId"] = rec["ReceiveItemId"] + offset
                shifted.append(r)
            page = paginate(shifted, pgnum, pgsiz)
            self._send_json({
                "TotalResults": len(shifted),
                "ResourceList": page,
            })
            return

        # --- inventory/stocksummaries ---
        if path == "inventory/stocksummaries":
            page = paginate(ALL_STOCK_SUMMARIES, pgnum, pgsiz)
            self._send_json({
                "TotalResults": len(ALL_STOCK_SUMMARIES),
                "Summaries": page,
            })
            return

        # --- inventory/facilities/{id}/locations ---
        match = re.match(r"inventory/facilities/(\d+)/locations", path)
        if match:
            facility_id = int(match.group(1))
            all_locations = generate_locations(facility_id, count=205)
            page = paginate(all_locations, pgnum, pgsiz)
            self._send_json({
                "TotalResults": len(all_locations),
                "ResourceList": page,
            })
            return

        # --- inventory ---
        if path == "inventory":
            page = paginate(ALL_INVENTORY, pgnum, pgsiz)
            self._send_json({
                "TotalResults": len(ALL_INVENTORY),
                "ResourceList": page,
            })
            return

        # --- orders ---
        if path == "orders":
            filtered = filter_by_rql(
                ALL_ORDERS, rql, "ReadOnly.LastModifiedDate"
            )
            page = paginate(filtered, pgnum, pgsiz)
            self._send_json({
                "TotalResults": len(filtered),
                "ResourceList": page,
            })
            return

        self._send_json({"error": "Not Found"}, 404)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_server(port=DEFAULT_PORT):
    server = HTTPServer(("0.0.0.0", port), MockAPIHandler)
    print(f"[MockAPI] 3PLCentral mock server running on http://localhost:{port}")
    print(f"[MockAPI] Press Ctrl+C to stop")

    def shutdown_handler(signum, frame):
        print("\n[MockAPI] Shutting down...")
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    server.serve_forever()
    server.server_close()
    print("[MockAPI] Server stopped.")


if __name__ == "__main__":
    port = DEFAULT_PORT
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        port = int(sys.argv[idx + 1])
    elif len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    run_server(port)
