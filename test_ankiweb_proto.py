"""Offline regression tests for the schema-driven protobuf codec."""

from __future__ import annotations

import unittest

from ankiweb_proto import ProtoError, decode, encode
from ankiweb_schema import SCHEMA, endpoint


class ProtoCodecTests(unittest.TestCase):
    def test_regression_endpoint_mappings(self) -> None:
        login = endpoint("/svc/account/login")
        self.assertEqual(login["response"], "AccountLoginResponse")
        self.assertEqual(
            [f["name"] for f in SCHEMA[login["response"]]["fields"]],
            ["status", "token"],
        )
        # get-addon-info resolves to {addon} (verified Oct 2026 against the
        # live bundle: k(sr,new xt(n),Pt,e)); the old None mapping was a
        # parser artifact.
        addon_info = endpoint("/svc/shared/get-addon-info")
        self.assertEqual(addon_info["response"], "SharedGetAddonInfoResponse")
        self.assertEqual(
            [f["name"] for f in SCHEMA[addon_info["response"]]["fields"]],
            ["addon"],
        )
        upload = endpoint("/svc/shared/upload-addon")
        self.assertEqual(upload["response"], "SharedUploadAddonResponse")

    def test_login_response_round_trip(self) -> None:
        message = "AccountLoginResponse"
        wire = bytes([0x08, 0x01, 0x12, 0x03]) + b"tok"
        decoded = decode(message, wire)
        self.assertEqual(decoded, {"status": 1, "token": "tok"})
        self.assertEqual(decode(message, encode(message, decoded)), decoded)

    def test_signed_scalar_and_packed_repeated(self) -> None:
        schema_name = "CodecTestMessage"
        field = {"no": 1, "name": "values", "type": "sint32", "wire": 0,
                 "repeated": True, "optional": False}
        SCHEMA[schema_name] = {"name": schema_name, "fields": [field]}
        try:
            encoded = encode(schema_name, {field["name"]: [-1, 0, 1]})
            self.assertEqual(decode(schema_name, encoded)[field["name"]], [-1, 0, 1])
        finally:
            del SCHEMA[schema_name]

    def test_unknown_fields_round_trip_without_corruption(self) -> None:
        # unknown field 99, length-delimited "xyz"
        raw = bytes([0x9A, 0x06, 0x03]) + b"xyz"
        decoded = decode("AccountCheckTermsResponse", raw)
        self.assertEqual(encode("AccountCheckTermsResponse", decoded), raw)

    def test_malformed_known_wire_type_is_not_misdecoded(self) -> None:
        with self.assertRaises(ProtoError):
            decode("AccountGetAccountStatusResponse", b"\x08\x01\x12\x03\xff")


if __name__ == "__main__":
    unittest.main()
