"""Run every notebook cell in order in a fresh Python process."""
from pathlib import Path
import os
import sys
import nbformat
from IPython.terminal.interactiveshell import TerminalInteractiveShell
from IPython.utils.capture import capture_output

ROOT = Path(__file__).resolve().parent
NOTEBOOK = next((ROOT / "notebooks").glob("*.ipynb"))


def main():
    os.chdir(ROOT)
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    shell = TerminalInteractiveShell.instance()
    shell.display_formatter.active_types = ["text/plain", "text/html", "image/png"]
    with capture_output():
        shell.run_line_magic("matplotlib", "inline")
    shell.user_ns["__name__"] = "__main__"
    count = 0
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        count += 1
        print(f"Running cell {count}...", flush=True)
        with capture_output() as captured:
            result = shell.run_cell(cell.source, store_history=True)
        if result.error_before_exec or result.error_in_exec:
            captured.show()
            result.raise_error()
        cell.execution_count = count
        cell.outputs = []
        for name, value in (("stdout", captured.stdout), ("stderr", captured.stderr)):
            if value:
                cell.outputs.append(nbformat.v4.new_output("stream", name=name, text=value))
        for output in captured.outputs:
            cell.outputs.append(nbformat.v4.new_output(
                "display_data", data=output.data, metadata=output.metadata))
        # Jupyter metadata must not retain machine-specific execution paths.
        cell.metadata = {}
    notebook.metadata.language_info = {"name": "python", "version": sys.version.split()[0]}
    nbformat.validate(notebook)
    nbformat.write(notebook, NOTEBOOK)
    from src.provenance import write_provenance
    write_provenance()
    print(f"Completed: {NOTEBOOK.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
