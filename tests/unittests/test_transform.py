import unittest

from tap_3plcentral.transform import (
    convert,
    convert_array,
    convert_json,
    remove_embedded_links,
    denest_embedded_readonly_nodes,
    transform_stock_summaries,
    transform_locations,
    transform_json,
)


class TestConvert(unittest.TestCase):
    """Tests for camelCase to snake_case conversion."""

    def test_simple_camel_case(self):
        self.assertEqual(convert("ResourceList"), "resource_list")

    def test_all_caps(self):
        self.assertEqual(convert("URL"), "url")

    def test_lower_case(self):
        self.assertEqual(convert("name"), "name")

    def test_mixed_case(self):
        self.assertEqual(convert("lastModifiedDate"), "last_modified_date")

    def test_single_word(self):
        self.assertEqual(convert("Order"), "order")

    def test_multiple_uppercase(self):
        self.assertEqual(convert("ReadOnly"), "read_only")

    def test_complex_name(self):
        self.assertEqual(convert("TotalResults"), "total_results")


class TestConvertArray(unittest.TestCase):
    """Tests for convert_array."""

    def test_simple_array(self):
        result = convert_array(["a", "b", "c"])
        self.assertEqual(result, ["a", "b", "c"])

    def test_array_with_dicts(self):
        result = convert_array([{"FirstName": "John", "LastName": "Doe"}])
        self.assertEqual(result, [{"first_name": "John", "last_name": "Doe"}])

    def test_nested_array(self):
        result = convert_array([[{"ItemId": 1}]])
        self.assertEqual(result, [[{"item_id": 1}]])

    def test_empty_array(self):
        result = convert_array([])
        self.assertEqual(result, [])


class TestConvertJson(unittest.TestCase):
    """Tests for convert_json."""

    def test_simple_json(self):
        result = convert_json({"FirstName": "John", "LastName": "Doe"})
        self.assertEqual(result, {"first_name": "John", "last_name": "Doe"})

    def test_nested_json(self):
        result = convert_json({"CompanyInfo": {"CompanyName": "Acme"}})
        self.assertEqual(result, {"company_info": {"company_name": "Acme"}})

    def test_json_with_list(self):
        result = convert_json({"OrderItems": [{"ItemId": 1}]})
        self.assertEqual(result, {"order_items": [{"item_id": 1}]})

    def test_empty_json(self):
        result = convert_json({})
        self.assertEqual(result, {})


class TestRemoveEmbeddedLinks(unittest.TestCase):
    """Tests for remove_embedded_links."""

    def test_remove_links(self):
        data = {"name": "test", "_links": {"self": "/api/test"}}
        result = remove_embedded_links(data)
        self.assertEqual(result, {"name": "test"})

    def test_remove_embedded(self):
        data = {"name": "test", "_embedded": {"items": [1, 2]}}
        result = remove_embedded_links(data)
        self.assertEqual(result, {"name": "test"})

    def test_remove_both(self):
        data = {
            "name": "test",
            "_links": {"self": "/api"},
            "_embedded": {"items": [1]},
        }
        result = remove_embedded_links(data)
        self.assertEqual(result, {"name": "test"})

    def test_nested_removal(self):
        data = {
            "name": "test",
            "child": {"value": 1, "_links": {"self": "/api/child"}},
        }
        result = remove_embedded_links(data)
        self.assertEqual(result, {"name": "test", "child": {"value": 1}})

    def test_list_input(self):
        data = [{"name": "a", "_links": {}}, {"name": "b", "_embedded": {}}]
        result = remove_embedded_links(data)
        self.assertEqual(result, [{"name": "a"}, {"name": "b"}])

    def test_non_dict_input(self):
        self.assertEqual(remove_embedded_links("hello"), "hello")
        self.assertEqual(remove_embedded_links(42), 42)
        self.assertIsNone(remove_embedded_links(None))


class TestDenestEmbeddedReadonlyNodes(unittest.TestCase):
    """Tests for denest_embedded_readonly_nodes."""

    def test_no_path(self):
        data = {"key": "value"}
        result = denest_embedded_readonly_nodes(data, path=None)
        self.assertEqual(result, data)

    def test_denest_readonly(self):
        data = {
            "ResourceList": [
                {
                    "order_id": 1,
                    "ReadOnly": {"creation_date": "2025-01-01", "status": "active"},
                }
            ]
        }
        result = denest_embedded_readonly_nodes(data, path="ResourceList")
        record = result["ResourceList"][0]
        self.assertEqual(record["creation_date"], "2025-01-01")
        self.assertEqual(record["status"], "active")
        self.assertNotIn("ReadOnly", record)


class TestTransformStockSummaries(unittest.TestCase):
    """Tests for transform_stock_summaries."""

    def test_extract_item_id(self):
        data = {
            "summaries": [
                {"item_identifier": {"id": 42, "sku": "SKU001"}, "quantity": 100}
            ]
        }
        result = transform_stock_summaries(data, "summaries")
        self.assertEqual(result["summaries"][0]["item_id"], 42)

    def test_missing_item_identifier(self):
        data = {"summaries": [{"quantity": 100}]}
        result = transform_stock_summaries(data, "summaries")
        self.assertIsNone(result["summaries"][0]["item_id"])


class TestTransformLocations(unittest.TestCase):
    """Tests for transform_locations."""

    def test_extract_ids(self):
        data = {
            "resource_list": [
                {
                    "location_identifier": {
                        "id": 10,
                        "name_key": {
                            "facility_identifier": {"id": 1}
                        },
                    }
                }
            ]
        }
        result = transform_locations(data, "resource_list")
        self.assertEqual(result["resource_list"][0]["location_id"], 10)
        self.assertEqual(result["resource_list"][0]["facility_id"], 1)

    def test_missing_identifiers(self):
        data = {"resource_list": [{}]}
        result = transform_locations(data, "resource_list")
        self.assertIsNone(result["resource_list"][0]["location_id"])
        self.assertIsNone(result["resource_list"][0]["facility_id"])


class TestTransformJson(unittest.TestCase):
    """Tests for the main transform_json pipeline."""

    def test_transform_json_generic(self):
        """Test generic transformation with camelCase conversion and link removal."""
        data = {
            "ResourceList": [
                {
                    "OrderId": 1,
                    "CustomerName": "Acme",
                    "_links": {"self": "/api/orders/1"},
                }
            ]
        }
        result = transform_json(data, "orders", "ResourceList")
        self.assertIn("resource_list", result)
        record = result["resource_list"][0]
        self.assertEqual(record["order_id"], 1)
        self.assertEqual(record["customer_name"], "Acme")
        self.assertNotIn("_links", record)

    def test_transform_json_stock_summaries(self):
        """Test stock_summaries specific transformation."""
        data = {
            "Summaries": [
                {
                    "ItemIdentifier": {"Id": 5, "Sku": "ABC"},
                    "Quantity": 50,
                }
            ]
        }
        result = transform_json(data, "stock_summaries", "Summaries")
        record = result["summaries"][0]
        self.assertEqual(record["item_id"], 5)

    def test_transform_json_locations(self):
        """Test locations specific transformation."""
        data = {
            "ResourceList": [
                {
                    "LocationIdentifier": {
                        "Id": 10,
                        "NameKey": {"FacilityIdentifier": {"Id": 1}},
                    }
                }
            ]
        }
        result = transform_json(data, "locations", "ResourceList")
        record = result["resource_list"][0]
        self.assertEqual(record["location_id"], 10)
        self.assertEqual(record["facility_id"], 1)


if __name__ == "__main__":
    unittest.main()
