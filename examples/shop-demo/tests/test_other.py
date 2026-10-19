import pytest

from shop.catalog import lookup
from shop.checkout import hold
from shop.inventory import reserve
from shop.notify import discount_message
from shop.orders import place_order
from shop.shipping import cost
from shop.tax import tax_on

from pace import pace


def test_catalog_lookup():
    pace("test_catalog_lookup")
    assert lookup("BOOK") == 12.0


def test_catalog_missing():
    pace("test_catalog_missing")
    with pytest.raises(KeyError):
        lookup("MISSING")


def test_inventory_reserve():
    pace("test_inventory_reserve")
    assert reserve(5, 2) == 3


def test_inventory_empty():
    pace("test_inventory_empty")
    with pytest.raises(ValueError):
        reserve(1, 2)


def test_shipping_standard():
    pace("test_shipping_standard")
    assert cost(1.5) == 6.5


def test_shipping_express():
    pace("test_shipping_express")
    assert cost(1.5, express=True) == 13.0


def test_tax_basic():
    pace("test_tax_basic")
    assert tax_on(10) == 1


def test_order_id():
    pace("test_order_id")
    assert place_order("PEN", 2.5)["sku"] == "PEN"


def test_notify_message():
    pace("test_notify_message")
    assert discount_message("SAVE5") == "Applied SAVE5"


def test_checkout_stock():
    pace("test_checkout_stock")
    assert hold(4, 1) == 3
