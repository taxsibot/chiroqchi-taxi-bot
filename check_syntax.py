import os
import py_compile
import sys

def check_syntax():
    errors = 0
    for root, dirs, files in os.walk('.'):
        # Prune directories in place to avoid traversing them
        dirs[:] = [d for d in dirs if d not in ('.venv', '.venv_old', '.git', '__pycache__', 'temp', 'scratch')]
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                try:
                    py_compile.compile(path, doraise=True)
                except py_compile.PyCompileError as e:
                    print(f"Syntax error in {path}:\n{e}")
                    errors += 1
    if errors == 0:
        print("No syntax errors found.")
    else:
        print(f"Found {errors} syntax errors.")
        sys.exit(1)

if __name__ == "__main__":
    check_syntax()
