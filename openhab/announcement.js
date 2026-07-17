// =============================================================================
// announcement.js — appliance TTS via the Ambiance binding's audio sink.
//
// On a `sayamplipi` update: Voice.say(msg, <ambiance controller sink>). openHAB's Piper
// synthesizes, the binding's PAAudioSink serves the audio + POSTs /api/announce, and the
// Ambiance service ducks the radio and plays it on ch0boost. No TTS-cache scraping, no
// ttsplay daemon — the standard openHAB TTS path. The siren overrides speech (dropped here
// while active; the Ambiance service also refuses speech during a siren).
// CUTOVER: replaces automation/jsr223/announcement.js.
// =============================================================================
const ruleName = "SayAmbiance";
const { items, rules, triggers, actions, time, cache } = require('openhab');

const SINK = "ambianceamplipi:controller:main";   // the controller Thing UID = the PA audio sink id
const ALARM_ITEM = "AlarmPanel_Siren_Active";
const DEDUP_MS = 30000;

function alarmActive() {
    try { return String(items.getItem(ALARM_ITEM).state) === 'ON'; } catch (e) { return false; }
}

function handleSay() {
    try {
        let msg = items.getItem('sayamplipi').state;
        if (!msg || msg === 'NULL' || msg === 'UNDEF') return;
        msg = msg.toString().trim();
        if (!msg) return;

        const now = time.ZonedDateTime.now().toInstant().toEpochMilli();
        const last = cache.private.get('lastMsg');
        const lastAt = Number(cache.private.get('lastAt')) || 0;
        if (msg === last && (now - lastAt) < DEDUP_MS) return;
        cache.private.put('lastMsg', msg);
        cache.private.put('lastAt', now);

        if (alarmActive()) { console.info(`${ruleName}: siren active, dropping "${msg}"`); return; }

        actions.Voice.say(msg.replace(/!important!/g, '').trim(), null, SINK);
        console.info(`${ruleName}: said -> ${SINK}  ("${msg}")`);
    } catch (e) {
        if (String(e.message || e).includes("Context is already closed")) return;
        console.error(`${ruleName}: ${e}`);
    }
}

rules.JSRule({
    name: ruleName,
    description: "Speak announcements via the Ambiance AmpliPi audio sink",
    triggers: [triggers.ItemStateUpdateTrigger('sayamplipi')],
    execute: handleSay
});

console.info(`${ruleName}: loaded`);
