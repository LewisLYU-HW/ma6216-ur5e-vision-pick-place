"""Small controlled physical baseline sweep; failures remain in per-trial logs."""
import json
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
cases=[('shift_left',.43,-.16,0.),('shift_right',.48,-.20,0.),('yaw_15',.45,-.19,.2617993877991494)]
results=[]
for name,x,y,yaw in cases:
    out=root/'artifacts/physical_variants'/name
    out.mkdir(parents=True,exist_ok=True)
    with (out/'run.log').open('w') as log:
        proc=subprocess.run([sys.executable,'-u',str(root/'scripts/run_physical_pick_place.py'),'--headless','--cube-xy',str(x),str(y),'--cube-yaw',str(yaw),'--output',str(out)],cwd=root,stdout=log,stderr=subprocess.STDOUT)
    summary=json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else {'error':'No result file'}
    results.append({'case':name,'x_m':x,'y_m':y,'yaw_rad':yaw,'exit_code':proc.returncode,**summary})
    print(json.dumps({k:v for k,v in results[-1].items() if k!='results'}),flush=True)
(root/'artifacts/physical_variants/summary.json').write_text(json.dumps(results,indent=2))
