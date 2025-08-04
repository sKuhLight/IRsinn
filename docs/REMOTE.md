# Remote platform

Example configuration:
```yaml
- platform: smartir
  name: Living Room IR Remote
  unique_id: lr_remote
  device_code: 1000
  controller_data: remote.broadlink
```

Supported service calls include `remote.send_command`, `remote.learn_command` and `remote.delete_command`.
