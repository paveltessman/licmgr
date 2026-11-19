# Activation API

Send `POST /activate` with `Content-Type: application/json`. The request body is an object with two required strings:

| Field         | Value                                                                                                                                          |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `license_key` | A case-sensitive key issued by the server CLI in the form `XXXX-XXXX-XXXX-XXXX`. Send it as issued, including the hyphens.                     |
| `device_id`   | The [identifier derived from the Linux machine ID](client.md#linux-device-identifier), encoded as exactly 64 lowercase hexadecimal characters. |

The server returns a JSON object containing `status`. For errors, it also returns a machine-readable `code`. Clients use the HTTP status and JSON fields to distinguish these responses.

| HTTP status | JSON body                                          | Client outcome    |
| ----------- | -------------------------------------------------- | ----------------- |
| 200         | `{"status":"activated"}`                           | Activated         |
| 200         | `{"status":"already_activated"}`                   | Already activated |
| 404         | `{"status":"error","code":"invalid_license"}`      | Error             |
| 409         | `{"status":"error","code":"device_limit_reached"}` | Error             |
| 422         | `{"status":"error","code":"invalid_request"}`      | Error             |

Return `invalid_request` for malformed JSON or a missing or invalid field, including a key whose shape differs from the four-group format. Return `invalid_license` for a correctly formatted key that the server has not issued. Treat transport failures, unexpected status codes, and malformed or unrecognized response bodies as client errors.

For a valid request, look up the license, then check whether the device is already registered for it. Return `already_activated` for a registered device even when the license is at capacity. For a new device, enforce the license's `max_devices` and record the activation atomically so concurrent requests cannot exceed the limit. Repeating the same request after a timeout is safe because a license and device pair can occupy only one slot.
