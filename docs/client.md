# Client behavior

The client uses a license key issued by the server to request activation for the device it is running on. It displays the outcome to the user.

## Activation flow

1. The client receives a license key issued by the server.
2. The client derives a device identifier from the Linux machine ID as described below.
3. The client sends the license key and device identifier to the [activation API](activation.md).
4. The server validates the request and applies the license's `max_devices` limit when activating a new device.
5. The client displays the outcome for the request.

| Outcome           | Meaning                                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| Activated         | The server activated this device for the first time.                                                             |
| Already activated | The license was already activated on this device.                                                                |
| Error             | The client could not identify the device or obtain a valid activation result, or the server rejected activation. |

The client exits with code 0 for either successful outcome and code 1 for an activation error. It uses a finite HTTP timeout and displays a readable error for connection failures, timeouts, and unexpected responses.

## Linux device identifier

1. Read `/etc/machine-id` as ASCII, strip surrounding whitespace, and require exactly 32 lowercase hexadecimal characters with at least one nonzero digit.
2. Decode the hexadecimal value to 16 bytes and compute HMAC-SHA-256 using the fixed application-specific key `b"licmgr/device-id/v1"`. Keep this key constant across client releases.
3. Send the lowercase hexadecimal digest as `device_id`. The raw machine ID stays local.

If the file is missing, unreadable, or invalid, display an error before sending the activation request.

A license slot corresponds to a Linux installation's machine ID. Reboots, OS updates, and hardware changes preserve the identifier as long as the machine ID stays the same. A reinstall that generates a new machine ID uses a new slot. Cloned systems that share a machine ID share the identifier. The server uses the client-supplied identifier to recognize repeat requests.
