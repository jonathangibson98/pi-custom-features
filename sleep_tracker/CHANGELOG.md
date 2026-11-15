# Changelog

## 1.0.0 - 2026-11-15

- First release. Track any `person`: weighted signals with a sleep confidence score, fall-asleep and wake levels, settle and
  wake times, must-be-true signals that wake instantly, night hours, optional naps and home-only tracking
- Signals suggested from the person's Companion app sensors (charging, Focus, activity, Android sleep confidence and screen)
  and a bedroom area's lights, TVs and motion sensors
- Bedtime is dated back to when the signals first agreed. Short wake-ups are interruptions of the same night
- MQTT entities: asleep, sleep status, confidence, last sleep (with history and a 7-night average), mark asleep / awake buttons,
  and Everyone asleep
- Web UI with live signals, recent nights, manual marking and deleting wrong nights
