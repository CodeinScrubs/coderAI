import subprocess
import os

patch = '''diff --git a/test_robust.py b/test_robust.py
--- a/test_robust.py
+++ b/test_robust.py
@@ -34,4 +34,4 @@
 def hello():
-    print("hi")
+    print("hello world")
     
'''
with open("test.patch", "w") as f:
    f.write(patch)

res = subprocess.run(["git", "apply", "--allow-empty", "test.patch"], capture_output=True, text=True)
print("Return:", res.returncode)
print("Stdout:", res.stdout)
print("Stderr:", res.stderr)
