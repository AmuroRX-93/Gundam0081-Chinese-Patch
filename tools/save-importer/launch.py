"""Entry point for bundled Python. Does not install anything on the host."""
from pathlib import Path
import os
import sys

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'runtime'
# PBS Tcl/Tk ships beside Python. Resolve the bundled script libraries after
# relocation instead of relying on a machine's Tcl installation.
for variable,filename in [('TCL_LIBRARY','init.tcl'),('TK_LIBRARY','tk.tcl')]:
    matches=list(RUNTIME.rglob(filename)) if RUNTIME.exists() else []
    if matches:
        os.environ[variable]=str(matches[0].parent)
sys.path.insert(0,str(ROOT))
if __name__=='__main__':
    import importer
    try:importer.main()
    except Exception as exc:
        print('操作停止：'+str(exc),file=sys.stderr)
        if len(sys.argv)==1:
            try:
                import tkinter.messagebox
                tkinter.messagebox.showerror('水天之泪存档导入器',str(exc))
            except Exception:pass
        sys.exit(1)
