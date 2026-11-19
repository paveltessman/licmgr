# About the project

This test assignment is a client–server licensing system. The server issues license keys with a configurable device limit and validates activation requests. The client requests activation and displays the result.

Server: fastAPI + sqlite.
Client: Linux Python script.

## Licensing flow

1. The server includes a CLI that issues new keys. When issuing a key, the operator can choose `max-devices`, the maximum number of devices that can activate the license.
2. The server issues the new key in the form `XXXX-XXXX-XXXX-XXXX`, which is then passed to the client.
3. The client uses the issued license key to request activation for its device.
4. The server validates the license for the request and returns the result.
5. The client shows one of three outcomes: activated, already activated, or error.

See the [activation API contract](activation.md) and [client behavior](client.md).
