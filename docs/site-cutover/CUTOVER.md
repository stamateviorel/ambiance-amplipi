# Ambiance AmpliPi — cutover runbook (Phase 4)

Switches the Pi from the old LMS/AmpliPi/squeezelite stack to **Ambiance AmpliPi** (a stripped
fork + a real openHAB binding), and repoints the existing music widget at the binding. Fully
reversible. **Do it supervised, with the alarm DISARMED and someone in a zone to listen.**
~5 min; rollback ~1 min.

## Preconditions
- [ ] `Alarm_State` is NOT armed (this touches the siren path).
- [ ] Someone present who can hear a zone (Main area).
- [ ] Binding is deployed + Active (bundle "Ambiance AmpliPi Binding").
- [ ] Full restore point exists: `misc/audio/backups/pre-ambiance-20260717-161003/` (+ off-box on the NAS).

## Order (Pi first, so the binding finds the controller ONLINE, then openHAB)

### 1. Pi goes live
```bash
ssh pi@192.168.1.138 'bash /home/pi/ambiance-amplipi/cutover-pi.sh'
```
Stops+disables LMS/amplipi/squeezelite + the superseded radio-* daemons → flips `ambiance.env`
to `rpi`/live + `mpd.conf`→ch0 → starts `ambiance-mpd` + `ambiance` (`rt.Rpi()` resets the preamps,
valid now that amplipi.service is stopped) + `ambiance-display` → enables + linger → plays VRT
Radio 1. Prints a health block + siren self-test.

### 2. openHAB rebind
```bash
bash /home/openhab/work/ambiance-amplipi/cutover-openhab.sh
```
Backs up + swaps `announcement.js` (→ `Voice.say` to the audio sink), `alarmpanel_output_hooks.js`
(→ `Ambiance_Siren`), `music.items` + `amplipi.items` (→ real `ambianceamplipi:*` channels), adds
`ambiance.things` (controller + 6 zones), disables `lyron.things` + `amplipi.things`.

### 3. Verify
- [ ] **Radio**: audible in a zone; station switch works (widget or `openhab:send SqueezeGeneralPlayFavorite "VRT Klara"`).
- [ ] **Announcement**: `openhab:send sayamplipi "test aankondiging"` → hear it over softened radio, no pop.
- [ ] **Screen**: station + album art + zones + clock.
- [ ] **Siren** (warn the room): `openhab:send AlarmPanel_Siren_Active ON` → alarm on all zones at full;
      `... OFF` → radio restores.
- [ ] **Widget** (`SqueezeMultiZoneControl`): master + per-zone volume/mute, station picker, now-playing +
      album cover, play/pause.
- [ ] **Music-follows-you**: `music_motion_control` powers a zone on motion without overriding a user mute.

## Rollback (any problem)
```bash
ssh pi@192.168.1.138 'bash /home/pi/ambiance-amplipi/rollback-pi.sh'   # old stack back
bash /home/openhab/work/ambiance-amplipi/rollback-openhab.sh           # old rules/items/things back
```
Old stack re-enabled, house.json restored, ambiance units returned to Phase-0/safe. If per-file
rollback is ever insufficient, restore wholesale from the Phase-0 snapshot (its RESTORE_INSTRUCTIONS.md).

## Soak (Phase 5-prep)
Leave the old stack installed-but-disabled ~1 week. Then optionally publish the fork + binding.

## What each piece became
| Old | New |
|---|---|
| LMS + squeezelite + amplipi.service (FastAPI + house.json) | ambiance.service (stripped fork) + ambiance-mpd |
| amplipi-display | ambiance-display (station/art/zones/clock) |
| squeezebox + amplipi openHAB bindings | **org.openhab.binding.ambianceamplipi** (real channels) |
| Voice.say → squeezebox sink | Voice.say → the binding's PAAudioSink → /api/announce |
| LMS siren loop | AlarmPanel_Siren_Active → Ambiance_Siren → /api/alarm |
| the music widget | unchanged — items just repointed |
