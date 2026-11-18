"""Pin the route-bound runtime independently of the historical adapter."""

ROUTE_ADAPTER_SHA256 = "91536c0a1b28962330f0833b05c103b72287deca78128502641844c4351797d8"
ROUTE_FIXTURE_REVISION = "40c24c07299525b14a7aad430b9671d042f95583"
ALL_ROUTE_FIXTURE_SHA256_BY_NAME = {
    "cases.json": "39efa95eeab735823d744a2cdcfce7f13c4ceebce68578512d0d5d3a7618704c",
    "config/recorded_decision_constants.py": "29e3cfa97351690f217862431d35c5ff0760413f452b4282c3a2b7628244cf97",
    "fixture.py": "6e7ab79fd18da1f8232c6884f820c07c8ee7db19235dec4cfca36dc0bdbd265e",
    "discovery/adapter.py": ROUTE_ADAPTER_SHA256,
    "discovery/config/discovery_constants.py": "1b9ba2129698ecf8471c425897be719e29af0ae5e324443c5d04caeb09f2eb20",
}
