# Client behavior

The client uses a license key issued by the server to request activation for the device it is running on. It displays the outcome to the user.

## Activation flow

1. The client receives a license key issued by the server.
2. The client collects information about the machine it runs on. This information is used to identify the device across activation requests.
3. The client sends the server an activation request using the key and an identifier based on the collected machine information. The server uses the identifier to distinguish a repeat request from an activation on another device.
4. The server validates the request and applies the license's `max_devices` limit when activating a new device.
5. The client displays the outcome for the request.

| Outcome   | Meaning                                                                                                                    |
| --------- | -------------------------------------------------------------------------------------------------------------------------- |
| Activated | The server activated the license for this device, or the license on this device is already activated.                      |
| Error     | The server rejected the request, such as when the key is invalid; or the client could not obtain a result from the server. |
