/*
 * Output-side hooks for alarmpanel state changes — AMBIANCE BINDING version.
 *
 *   1. AlarmPanel_Siren_Active -> Ambiance_Siren (bound to ambianceamplipi:controller:main:siren).
 *      The binding POSTs /api/alarm; the Ambiance service pauses the radio, drives all zones to
 *      full/unmuted, and loops alarm.wav on ch0boost. Release restores.
 *   2. Alarm_State -> ARMED_AWAY (or all_off_switch_main_area ON) -> away kill list
 *      (SqueezeGeneralPower=OFF now stops the radio via the binding's controller:power channel).
 *   3. Daily silent siren self-test via the Ambiance /api/alarm/selftest (decode-only, no sound).
 *
 * CUTOVER: replaces automation/jsr223/alarmpanel_output_hooks.js.
 */
'use strict';

const ruleName = "AlarmPanel Output Hooks";
const { items, rules, triggers, cache, actions } = require('openhab');
const { sendBroadcastNotification } = require('shared_utils');

const AMBIANCE = 'http://192.168.1.138:8080';

// ============================================================================
// 1. Siren -> Ambiance_Siren (binding channel)
// ============================================================================
function verifySiren(attempt) {
    setTimeout(() => {
        try {
            const s = items.getItem('AlarmPanel_Siren_Active');
            if (!s || String(s.state) !== 'ON') return;                 // released meanwhile
            const amb = items.getItem('Ambiance_Siren');
            if (amb && String(amb.state) === 'ON') {
                console.info(`${ruleName}: siren VERIFIED engaged (attempt ${attempt})`);
                return;
            }
            if (attempt < 2) {
                console.warn(`${ruleName}: siren NOT engaged — retrying`);
                items.getItem('Ambiance_Siren').sendCommand('ON');
                verifySiren(attempt + 1);
                return;
            }
            console.error(`${ruleName}: siren STILL not engaged after retry`);
            sendBroadcastNotification('🚨 SIRENE FAALT: alarm engageert niet op de Ambiance-controller — controleer de Pi!', 'alarm', 'alarm-siren-fail', 'Alarm sirene defect');
        } catch (e) {
            if (String(e.message || e).includes('Context is already closed')) return;
            console.error(`${ruleName}: siren verify error: ${e}`);
        }
    }, 4000);
}

rules.JSRule({
    id: "alarmpanel_audio_hooks_v2",
    overwrite: true,
    name: "AlarmPanel Audio Hooks",
    description: "On AlarmPanel_Siren_Active change: drive Ambiance_Siren (binding controller:siren).",
    triggers: [triggers.ItemStateChangeTrigger("AlarmPanel_Siren_Active")],
    execute: (event) => {
        try {
            const newState = event && event.newState != null ? String(event.newState) : null;
            console.info(`${ruleName}: AlarmPanel_Siren_Active -> ${newState}`);
            if (newState === 'ON') {
                items.getItem('Ambiance_Siren').sendCommand('ON');
                console.warn(`${ruleName}: 🚨 Ambiance siren ENGAGED`);
                verifySiren(1);
            } else if (newState === 'OFF') {
                items.getItem('Ambiance_Siren').sendCommand('OFF');
                console.info(`${ruleName}: Ambiance siren released`);
            }
        } catch (e) {
            if (String(e.message || e).includes('Context is already closed')) return;
            console.error(`${ruleName}: audio hooks ${e.message || e}`);
        }
    }
});

// ============================================================================
// 2. Away mode kill list (SqueezeGeneralPower=OFF stops the radio via the binding)
// ============================================================================
const AWAY_TARGETS = [
    { name: "Disable_office_detector_constant", cmd: "ON" },
    { name: "Block_Main_area_detector",         cmd: "ON" },
    { name: "Block_Main_area_up_detector",      cmd: "ON" },
    { name: "g_general_lights",                 cmd: "OFF" },
    { name: "Tv_office_SendKey",                cmd: "KEYCODE_SLEEP" },
    { name: "Tv_office2_SendKey",               cmd: "KEYCODE_SLEEP" },
    { name: "SqueezeGeneralPower",              cmd: "OFF" },
    { name: "Office_back_street_airco_power",   cmd: "OFF" },
    { name: "Office_front_street_airco_power",  cmd: "OFF" },
    { name: "Showroom_airco_power",             cmd: "OFF" }
];

function applyAwayState() {
    const setOne = ({ name, cmd }) => {
        try {
            const item = items.getItem(name);
            if (item && String(item.state) !== String(cmd)) {
                console.info(`${ruleName}: -> ${name} = ${cmd}`);
                item.sendCommand(cmd);
            }
        } catch (e) {}
    };
    AWAY_TARGETS.forEach(setOne);
    setTimeout(() => {
        try { AWAY_TARGETS.forEach(setOne); }
        catch (e) { if (!String(e.message || e).includes('Context is already closed')) console.warn(`${ruleName}: away re-check failed: ${e.message || e}`); }
    }, 10000);
}

rules.JSRule({
    id: "alarmpanel_away_mode_v3",
    overwrite: true,
    name: "AlarmPanel Away Mode",
    description: "On Alarm_State=ARMED_AWAY or all_off_switch_main_area ON, send the away-mode kill list.",
    triggers: [
        triggers.ItemStateChangeTrigger("Alarm_State"),
        triggers.ItemStateChangeTrigger("all_off_switch_main_area", "OFF", "ON")
    ],
    execute: (event) => {
        try {
            const newState = event && event.newState != null ? String(event.newState) : null;
            const triggeredItem = event && event.itemName ? String(event.itemName) : null;
            let alarmState; try { alarmState = String(items.getItem("Alarm_State").state); } catch (e) { alarmState = null; }
            let allOff; try { allOff = String(items.getItem("all_off_switch_main_area").state); } catch (e) { allOff = null; }
            const armedAway = alarmState === "ARMED_AWAY" || (triggeredItem === "Alarm_State" && newState === "ARMED_AWAY");
            const allOffOn  = allOff === "ON" || (triggeredItem === "all_off_switch_main_area" && newState === "ON");
            if (!armedAway && !allOffOn) return;
            console.info(`${ruleName}: applying away kill list (alarmState=${alarmState}, allOff=${allOff})`);
            applyAwayState();
        } catch (e) {
            if (!String(e.message || e).includes('Context is already closed')) console.error(`${ruleName}: away mode ${e.message || e}`);
        }
    }
});

// ============================================================================
// 3. Daily SILENT siren self-test (Ambiance /api/alarm/selftest — no sound)
// ============================================================================
function runSirenSelfTest() {
    try {
        const sirenItem = items.getItem('AlarmPanel_Siren_Active');
        if (sirenItem && String(sirenItem.state) === 'ON') { console.info(`${ruleName}: self-test skipped (real alarm active)`); return; }
        let ok = false;
        try {
            const resp = actions.HTTP.sendHttpGetRequest(AMBIANCE + '/api/alarm/selftest', 8000);
            ok = resp ? (JSON.parse(resp).ok === true) : false;
        } catch (e) { ok = false; }
        if (ok) {
            console.info(`${ruleName}: ✅ siren self-test OK (silent)`);
        } else {
            console.error(`${ruleName}: 🚨 siren SELF-TEST FAILED`);
            sendBroadcastNotification('🚨 Sirene self-test GEFAALD: alarm-audiopad op de Ambiance-controller faalt. Alarm zou STIL zijn bij inbraak!', 'alarm', 'alarm-siren-selftest', 'Alarm sirene self-test');
        }
    } catch (e) {
        console.error(`${ruleName}: self-test error: ${e}`);
    }
}

rules.JSRule({
    name: "Alarm Siren Daily Self-Test",
    description: "Silent daily check that the Ambiance siren audio path works; notifies only on failure",
    triggers: [triggers.GenericCronTrigger("0 0 13 * * ?")],
    execute: runSirenSelfTest
});

console.info(`${ruleName}: loaded (3 rules: audio-hooks, away-mode, siren-selftest) — Ambiance binding backend`);
