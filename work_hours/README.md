# Work Hours Tracker

Logs how long each person spends in the work zones you pick for them, and
saves it to a separate CSV file named after each person.

- Add the people you want to track and pick their work zones from a sidebar page, no YAML needed
- Every person gets their own zones, so people can work at different locations
- One file per person, named after them (`Alex_Smith.csv`, `Sam.csv`, ...)
- MQTT device with an hours sensor per person: state is the current pay period, attributes keep the history
- Each person gets their own pay period (start day and number of weeks), set on the sidebar page
- Choose the save folder and how long to keep data in the add-on options
- Grace period so GPS wobble doesn't chop a shift in half
- Shifts that cross midnight are split so daily totals stay right

See the **Documentation** tab for setup and details.
