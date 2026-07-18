# openHAB glue (reference configuration)

The exact files this site runs — adapt names/IPs to yours:

| File | What |
|---|---|
| `ambiance.things` | `controller` bridge + six `zone` things for the `ambianceamplipi` binding |
| `music.items` | controller items: transport, source (radio/Spotify), volume, now-playing, cover, siren, health |
| `amplipi.items` | per-zone power/volume/mute items |
| `announcement.js` | text item -> `Voice.say(...)` via the binding's PA audio sink (TTS announcements) |
| `ambiance_health_notify.js` | push notification when the controller's audio health degrades/recovers |
| `alarmpanel_output_hooks.js` | burglar-siren integration: engage + verify + daily silent self-test |
| `widgets/SqueezeMultiZoneControl.yaml` | MainUI widget: now-playing + cover, transport, source chips, station picker, per-zone popup |

The binding lives in the openHAB add-ons tree as `org.openhab.binding.ambianceamplipi`
(branch `ambianceamplipi` on [stamateviorel/openhab-addons](https://github.com/stamateviorel/openhab-addons)).
