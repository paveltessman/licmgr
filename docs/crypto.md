# Activation payload encryption

The activation client will encrypt the entire request payload before sending it. The server will decrypt the payload before validating it and processing the activation. This document specifies the planned application-layer encryption for the [activation API](activation.md).

## HPKE suite

Use [RFC 9180 HPKE Base mode](https://www.rfc-editor.org/rfc/rfc9180.html) on both sides through Python's [`cryptography` HPKE API](https://cryptography.io/en/stable/hazmat/primitives/hpke/). The suite uses DHKEM(X25519, HKDF-SHA256), HKDF-SHA256, and AES-128-GCM. Both sides pass `b"license-activation-v1"` as the HPKE `info` value.

## Request format

1. The client serializes the object containing `license_key` and `device_id` as UTF-8 JSON and encrypts those bytes with `Suite.encrypt()` and the server's public key.
2. The client base64-encodes the returned `enc || ct` bytes using standard base64 with padding and sends them in the `ciphertext` field of a JSON envelope. The envelope has an integer `version` field set to `1`. The client sends the envelope to the existing activation endpoint with `Content-Type: application/json`.
3. The server validates the envelope, checks the version, decodes the base64, and opens the resulting bytes with `Suite.decrypt()` and the server's private key.
4. After successful decryption, the server parses and validates the inner JSON and passes its fields to the existing activation service. Malformed envelopes, unsupported versions, decryption failures, and invalid inner payloads return HTTP 422 with `invalid_request`.
