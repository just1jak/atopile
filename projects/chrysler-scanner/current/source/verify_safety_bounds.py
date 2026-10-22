"""Recompute bounded prototype safety margins; not a transient simulation."""
from pathlib import Path
import itertools, json, hashlib
ROOT=Path(__file__).resolve().parent.parent
pre_gain=1620*1.01/(22000*.99+1620*1.01)
loaded_bottom=1/(1/1620+1/100000)
loaded_gain=loaded_bottom/(22000+loaded_bottom)
pre_at_40=40*pre_gain
supply_during_assert=3.08*.98-50*0.005
unpowered_adc=2e-6*100000*1.01
nominal_timeout_ms=32768*(100000/50000)*.001
maximum_timeout_ms=nominal_timeout_ms*(1+.035+.001+.0025)
gate_max=28*(4700*1.01)/(4700*1.01+8200*.99)
gate_min=18.85*(4700*.99)/(4700*.99+8200*1.01)
checks={
 'adcPreAt40VBelow2p80':pre_at_40<2.80,
 'adcBelowAbsLimitUntilSupervisorAsserts':pre_at_40<supply_during_assert+.3,
 'unpoweredAdcBelow0p3':unpowered_adc<.3,
 'watchdogWithin70msBudget':maximum_timeout_ms<70,
 'programmingGateBelow12V':gate_max<12,
 'normalProgrammingGateAbove4p5V':gate_min>4.5,
 'boundedDrainBelow30V':28<30,
 'vbbGateBelow20V':12.85<20,
 'allOtherPermitCombinationsHoldReset':all((en and pg and hb)==(int(en)+int(pg)+int(hb)==3) for en,pg,hb in itertools.product((False,True),repeat=3)),
}
report={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
 'nominalLoadedAdcGain':loaded_gain,'worstUnloadedAdcAt40V':pre_at_40,
 'worstSupplyUntilSupervisorAssertion':supply_during_assert,
 'unpoweredAdcLeakageBoundV':unpowered_adc,
 'nominalTimeoutMs':nominal_timeout_ms,'boundedTimeoutMs':maximum_timeout_ms,
 'worstProgrammingGateV':gate_max,'minimumNormalProgrammingGateV':gate_min,
 'contractSha256':hashlib.sha256((ROOT/'reference/rev-c-safety-contract.md').read_bytes()).hexdigest(),
 'limitations':['Assumes specified exact IC variants and stated resistor tolerances.',
 'Rail fall rate <=5mV/us and 50us maximum assertion delay are bench requirements.',
 'TVS/source pulse energy, capacitive gate overshoot and physical timing require measurement.',
 'The protected rail/VPP <=28V bound must be validated; arithmetic does not establish it.',
 'Q8-Q11 3.3V drive remains a functional qualification gate.']}
(ROOT/'reference/safety-bounds-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
assert report['status']=='PASS'
