"""Print two contrasting student journeys (same sample syllabus, different answers).

    python scripts/simulate_journeys.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dissdisc import service  # noqa: E402
from dissdisc.simulate import LABOUR_POLICY, MACRO_THEORY, UNCERTAIN, run_persona  # noqa: E402

for persona in (LABOUR_POLICY, MACRO_THEORY, UNCERTAIN):
    state, run = run_persona(persona, seed=11)
    pack = service.pack_for(state)
    bundle = service.results(state, run)
    print("=" * 100)
    print(persona["name"], f"— {len(run.history)} tasks, stopped: {run.stop_reason}")
    for h in run.history:
        chosen = h.response.selected_option_id or "(unsure)"
        print(f"  {h.spec.step_index + 1:>2}. [{h.spec.selection_reason}] {h.spec.id} -> {chosen}")
    if bundle.overall_notice:
        print("  NOTICE:", bundle.overall_notice)
    for rec in bundle.recommendations:
        t = pack.territory(rec.territory_id)
        print(f"  #{rec.rank} {t.label}  [{rec.evidence_label}]")
        for r in rec.reasons:
            print(f"       - ({r.kind}) {r.text}")
