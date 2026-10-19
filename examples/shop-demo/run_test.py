import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

MODULES = {
    "test_percent_discount": "test_pricing",
    "test_stack_discounts": "test_pricing",
    "test_coupon_discount": "test_pricing",
    "test_bulk_discount": "test_pricing",
    "test_zero_percent": "test_pricing",
    "test_price_floor": "test_pricing",
    "test_rounding": "test_pricing",
    "test_full_price": "test_pricing",
    "test_pricing_audit": "test_pricing",
    "test_checkout_percent": "test_checkout",
    "test_checkout_bulk": "test_checkout",
    "test_order_discounted_total": "test_checkout",
    "test_tax_after_discount": "test_checkout",
    "test_notify_on_discount": "test_checkout",
    "test_catalog_lookup": "test_other",
    "test_catalog_missing": "test_other",
    "test_inventory_reserve": "test_other",
    "test_inventory_empty": "test_other",
    "test_shipping_standard": "test_other",
    "test_shipping_express": "test_other",
    "test_tax_basic": "test_other",
    "test_order_id": "test_other",
    "test_notify_message": "test_other",
    "test_checkout_stock": "test_other",
}


if __name__ == "__main__":
    module = importlib.import_module(MODULES[sys.argv[1]])
    getattr(module, sys.argv[1])()
