import subprocess
import os

def extract_conflicts():
    result = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], capture_output=True, text=True)
    files = result.stdout.strip().split("\n")
    if not files or files == [""]:
        print("No conflicts found.")
        return
    
    with open("conflict_report.txt", "w", encoding="utf-8") as out:
        for f in files:
            if not os.path.exists(f): continue
            out.write(f"=== {f} ===\n")
            with open(f, "r", encoding="utf-8", errors="ignore") as file:
                lines = file.readlines()
            
            in_conflict = False
            for line in lines:
                if line.startswith("<<<<<<< "):
                    in_conflict = True
                if in_conflict:
                    out.write(line)
                if line.startswith(">>>>>>> "):
                    in_conflict = False
                    out.write("\n")

if __name__ == "__main__":
    extract_conflicts()
