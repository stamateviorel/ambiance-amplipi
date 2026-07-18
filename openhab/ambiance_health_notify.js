// =============================================================================
// ambiance_health_notify.js — push a mobile notification when the Ambiance audio
// subsystem degrades or recovers.
//
// Driven natively by the ambianceamplipi binding's health channels (Ambiance_Health_OK +
// Ambiance_Health), populated from the controller's /api/status.health. The controller
// already self-heals a dropped radio stream and a wedged preamp; this only alerts when a
// problem PERSISTS (self-heal could not fix it). Replaces the retired amplipi-radio-watchdog
// REST push bridge — no rule polls the Pi anymore, the binding does.
//
// Dedup: change-triggered — a steady problem pushes ONCE; flapping within COOLDOWN_MS is
// collapsed into one push; a single recovery push on the OK transition.
// =============================================================================
const ruleName = "AmbianceHealthNotify";
const { items, rules, triggers } = require("openhab");
const { sendBroadcastNotification } = require("shared_utils");

const COOLDOWN_MS = 30 * 60 * 1000; // 30 min between repeat problem pushes

function memo() {
    globalThis._ambianceHealthMemo = globalThis._ambianceHealthMemo || { lastPushAt: 0, lastState: null };
    return globalThis._ambianceHealthMemo;
}

function doWork() {
    try {
        const ok = String(items.Ambiance_Health_OK.state) === "ON";
        const detail = String(items.Ambiance_Health.state || "").trim();
        const m = memo();
        const now = Date.now();

        if (!ok) {
            // audio degraded and self-heal could not fix it — alert (with cooldown)
            if (m.lastState !== "DEGRADED" || (now - m.lastPushAt) > COOLDOWN_MS) {
                sendBroadcastNotification("🔇 Audio probleem: " + (detail || "onbekend"),
                    "soundvolume", "ambiance-health", "Ambiance AmpliPi");
                m.lastPushAt = now;
            }
            m.lastState = "DEGRADED";
        } else {
            // recovered — push once, only if we had actually reported a problem
            if (m.lastState === "DEGRADED") {
                sendBroadcastNotification("🔊 Audio hersteld", "soundvolume", "ambiance-health", "Ambiance AmpliPi");
            }
            m.lastState = "OK";
        }
    } catch (e) {
        if (String(e.message || e).includes("Context is already closed")) return;
        console.error(`${ruleName}: ${e}`);
    }
}

rules.JSRule({
    name: ruleName,
    description: "Pushes when the Ambiance audio subsystem (radio/preamp) degrades or recovers.",
    triggers: [triggers.ItemStateChangeTrigger("Ambiance_Health_OK")],
    execute: doWork
});

console.info(`${ruleName}: loaded`);
