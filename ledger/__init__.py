"""MANEUVER LEDGER: Starlink manoeuvres reconstructed from public orbit data.

Modules, in the order the pipeline uses them:

    sources    read DODGE's recorded day files (checked against its sealed manifests)
    elements   turn each element set into SGP4 mean elements at a chosen time
    detect     compare successive element sets, calibrate noise, flag manoeuvres
    classify   decide what each manoeuvre was for (raising, lowering, on-station)
    fleet      the FCC reference numbers and fleet sizes, each with its source
    reconcile  annualised rates with error bars, side by side with the FCC
    synth      synthetic orbits with injected burns, for tests and detection limits
    page       the static results page (inline SVG, no scripts, no third parties)
    pipeline   the command line that runs all of the above
"""
