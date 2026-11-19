# Client behavior

The client uses a license key issued by the server to request activation for the device it is running on. It displays the outcome to the user.

## Activation flow

1. The client receives a license key issued by the server.
2. The client derives a device identifier from the Linux kernel release, CPU architecture, logical CPU count, and MAC address.
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

1. Read the Linux kernel release with `platform.release()`, CPU architecture with `platform.machine()`, and system logical CPU count with `os.cpu_count()`.
2. Read MAC addresses from `/sys/class/net`, skipping the loopback interface and any unreadable, malformed, all-zero, or multicast address. Normalize valid addresses to lowercase and select the lexicographically smallest one. Virtual interfaces can qualify.
3. Encode the four values in that order as a compact UTF-8 JSON array, then compute HMAC-SHA-256 with the fixed application-specific key `b"licmgr/device-id/v2"`. Send the 64-character lowercase hexadecimal digest as `device_id`. The raw values stay local.

If a required value is unavailable, the client displays an error before sending the activation request.

The server recognizes repeat activations by the resulting identifier. Switching from the previous machine-ID scheme changes the identifier for existing installations. A kernel update or a change in CPU architecture, logical CPU count, or the selected MAC address also changes it. A changed identifier requires a new license slot and can hit the device limit.
