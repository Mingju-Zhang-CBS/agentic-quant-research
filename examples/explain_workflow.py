"""Run from the repository after installing its package."""
import pandas as pd
from agentic_quant_research.core import admit, calculate_factor, date_split, default_proposals, generate_market, validate_market
panel=validate_market(generate_market(assets=5,sessions=180,seed=91))
status,accepted=admit(default_proposals())
factors=pd.DataFrame({p['id']:calculate_factor(panel,p['expression']) for p in accepted})
labels,masks,split=date_split(panel,factors)
assert all(not (masks[a] & masks[b]).any() for a,b in [('train','validation'),('train','confirmation'),('validation','confirmation')])
assert status.status.tolist()==['ADMITTED']*3+['DUPLICATE','REJECTED','REJECTED']
print(status.to_string(index=False));print(split)
