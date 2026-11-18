# FAQ

## About HomeBatteryAssist {#about}

??? question "Does HomeBatteryAssist control my battery?"
    **Not yet.** In this phase of development it only reads, forecasts and advises; the integration that controls your battery (e.g. Omnibattery) keeps doing so undisturbed. Controlling batteries itself is the goal: the control layer and its safety (release on every error, a watchdog, limits) are built, but not active. Until then *virtual batteries* follow the plan as a simulation, so you can see what it would do. Each battery also has a [test control](measuring.md#test-control-switched-off-for-now) (*Test: charge / discharge / stop*) for testing control by hand later; it is switched off as well.

??? question "Can it run next to Omnibattery or my battery's own app?"
    Yes. HomeBatteryAssist reads the battery through the entities of its integration and never opens its own connection to it, so nothing competes. Grid meters are only read directly when that is passive or through a read-only interface that allows any number of clients (HomeWizard P1 API, SMA Speedwire multicast).

??? question "What is a virtual battery?"
    A simulated battery that runs live next to your real ones and follows the chosen plan mode, with the real measurements of your home: phase protection, peak shaving and losses included. It has the same sensors and dashboard card as a real battery. Use it to see what a (bigger or extra) battery would do and bring, or to try a plan mode safely. Its name always ends with "(virtual)". Made the [twin](measuring.md#twin-of-a-real-battery) of your real battery, it runs in its place, so you can compare HomeBatteryAssist's plan with your battery's own control day by day.

??? question "Which plan mode should I choose?"
    - **Zero on the meter**: the battery stores your solar surplus and supplies the house when there is a shortage; it never charges from or supplies to the grid on purpose. Simple and predictable.
    - **Arbitrage**: cost-optimal for your own use; may also charge from the grid when that is cheaper than using the grid later (e.g. at night for the evening peak). Needs dynamic prices.
    - **Full arbitrage**: like arbitrage, but may also supply the grid when the export price makes that worthwhile.

    All modes are always calculated: the **Return** tab shows what each would bring, so you can compare before choosing.

## Plans and forecasts {#plans}

??? question "Why does the battery do nothing right now?"
    Read **Why** on the Overview tab: it tells what the plan does until when, and why. Common reasons: the battery is as empty as set (minimum or reserve), charging does not pay now (the price difference is too small after losses and wear), the energy is kept for a more expensive moment later, or a phase is at its limit.

??? question "Why did the planned charging move or disappear?"
    The plan is recalculated every 15 minutes (and when new prices arrive). New prices, a changed consumption or solar forecast, or another **plan mode** change it. Zero on the meter never charges from the grid — after switching from arbitrage to zero on the meter, a night charge disappears. *Why* explains each new plan.

??? question "Why does arbitrage keep energy for days?"
    When later prices are expected to be higher (e.g. the weekend), the energy is worth more then, and there is little sun to refill the battery. Prices further ahead are often *estimates* (dashed in the charts); when the published prices differ, the plan adapts.

??? question "What happens when there is suddenly more or less sun than forecast?"
    The batteries follow the solar surplus that is really there, not the forecast. More sun: the surplus is stored on top of the plan (never from the grid). Less sun: a charge the plan expected from the sun is only made as far as the sun is really there — the grid does not fill in; a planned charge from the grid goes on. The batteries react at once; *Why* tells it after 5 minutes, and the plan is recalculated every quarter of an hour with the real state of charge. The threshold (300 W) and the wait (5 min) are settings. See [Planning: when the sun differs from the forecast](planning.md#when-the-sun-differs-from-the-forecast).

??? question "What are the dashed lines in the charts?"
    Forecasts and estimates: the expected consumption and solar power, the planned state of charge and, for prices, estimated (not yet published) prices. Solid lines are measured or published values.

??? question "Right after a restart there is no forecast — is something wrong?"
    No. Other integrations (prices, solar forecast) may need a minute after a restart; HomeBatteryAssist retries every minute and only reports *no prices* when it lasts longer than 5 minutes.

??? question "Can I recalculate by hand?"
    Yes: the **Recalculate** button on the dashboard, the button entity, or the action `homebatteryassist.recalculate`. A recalculation by hand always shows the current plan in *Why*.

??? question "The consumption forecast is off. What can I do?"
    Give it time: it learns from your history and corrects itself where it is consistently off (see *Accuracy*). Import your history ([Getting started, step 7](getting-started.md#step-7-import-your-history)); add big loads such as an EV charger as an **excluded device**; add heat pumps and air conditioners as **heating/cooling** with a weather source. For holidays or guests, use the **vacation mode** or the action `homebatteryassist.adjust_forecast`.

## Measuring {#measuring}

??? question "The house consumption looks wrong."
    House consumption = grid (all phases) + solar − excluded devices − battery power. Check that every solar inverter is added as a **PV source**, that the battery's **power direction** (positive = charging or discharging) is right, and that each sensor is used only once.

??? question "Which grid meter is best?"
    A meter that is read directly (HomeWizard P1, SMA Home Manager, Shelly, Iammeter): about one value per second, with current and voltage per phase where the meter sends them. Sensors of another integration work too, but update less often.

??? question "Why does phase protection use current?"
    The main fuse reacts to current, not power. With a low power factor (standby devices, chargers) a phase can carry more current than its power suggests. HomeBatteryAssist uses the measured current where the meter sends it, else power / voltage, else power / 230 V.

## Help and feedback {#help}

??? question "Where do I report a problem or an idea?"
    On [GitHub issues](https://github.com/mvanrijnen/HomeBatteryAssist/issues). Add the **diagnostics** (integration page → ⋮ → *Download diagnostics*) and, if useful, a screenshot of *Why*.

??? question "How do I go back to the default settings?"
    **Configure → Back to the default settings** resets every setting; where the prices and the solar forecast come from is kept.

??? question "In which languages is HomeBatteryAssist available?"
    English and Dutch: the screens follow the language of your Home Assistant profile, and this documentation follows your browser (switch at the top).
