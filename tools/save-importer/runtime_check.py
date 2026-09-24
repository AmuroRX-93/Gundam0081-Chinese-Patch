"""Non-destructive CI/runtime smoke test. No live save access."""
from pathlib import Path
import sys,json,platform,hashlib,importlib.util
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
import launch
import tkinter as tk
import importer
app=tk.Tk();app.withdraw();app.update()
info={'python':platform.python_version(),'architecture':platform.machine(),'platform':platform.platform(),'tk':app.tk.call('info','patchlevel'),'runtime_prefix':str(Path(sys.prefix).name),'saves_checked':len(importer.read_catalog())}
app.destroy()
assert Path(sys.prefix).resolve()==(root/'runtime').resolve(),sys.prefix
assert sys.version_info>=(3,10)
assert info['saves_checked']==4
print(json.dumps(info,ensure_ascii=False,indent=2))
