## OVMS Command Interface

The OVMS module provides a command interface accessible through MQTT. To use commands, you need to have the OVMS Server V2 protocol active on your module.

![image](https://github.com/user-attachments/assets/74e3c80e-995b-460e-a6db-c1564bfb358e)

### Command Requirements

1. **V2 Server Connection**: Commands work through the V2 server protocol. Ensure this is enabled in your OVMS module configuration.
2. **MQTT Topic Structure**: Commands are sent to `{prefix}/{username}/{vehicle_id}/client/rr/command/{command}`
3. **Predefined Commands**: Commands are predefined in the OVMS system, not arbitrary values

### Common OVMS Commands

Here are essential OVMS commands you can use:

| Command | Description |
|---------|-------------|
| `stat` | Show vehicle status summary |
| `charge` | Control charging (status, start, stop) |
| `climate` | Control climate system |
| `location list` | List saved locations |
| `metrics list` | List available metrics |
| `lock` | Lock the vehicle |
| `unlock` | Unlock vehicle |
| `valet`/`unvalet` | Control valet mode |
| `homelink` | Activate homelink buttons |
| `wakeup` | Wake up the vehicle |

### Using the Command Service

You can send commands using the `ovms.send_command` service:

```yaml
service: ovms.send_command
data:
  vehicle_id: your_vehicle_id
  command: "charge"
  parameters: "status"
```

For commands with subcommands, include both parts:

```yaml
service: ovms.send_command
data:
  vehicle_id: your_vehicle_id
  command: "metrics"
  parameters: "list v.b.*"  # List all battery metrics
```

### Command UI (Recommended Implementation)

This integration would benefit from a dedicated command UI that:

1. Provides a dropdown of available commands
2. Dynamically shows parameter options for selected commands
3. Displays command responses directly in the UI
4. Maintains command history

Until such UI is implemented, you can use the service with custom cards or Developer Tools.

### Command Response

When sending commands through MQTT, responses come back on the corresponding response topic:
`{prefix}/{username}/{vehicle_id}/client/rr/response/{command}`

The integration processes these responses and makes them available in service call results.
