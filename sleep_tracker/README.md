# Sleep Tracker

Home Assistant add-on that tracks whether chosen people are asleep. It weighs several signals at once (phone charging,
Sleep Focus, phone not moving, bedroom lights, TV, motion) instead of trusting one, with settle and wake times, instant wake
signals, and bathroom trips counted as interruptions instead of new nights.

- `binary_sensor.<name>_asleep`, sleep status, confidence and last-night sensors over MQTT, plus **Everyone asleep**
- Last night's bedtime, wake time, interruptions and 7-night average, with a 14-night history
- **Mark asleep / Mark awake** buttons for automations
- Set up from the sidebar, with signals suggested from each person's phone and bedroom

See [DOCS.md](DOCS.md).
