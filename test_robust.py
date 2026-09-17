def robust_replace(text: str, old: str, new: str) -> str:
    if old in text:
        return text.replace(old, new)
        
    text_lines = text.splitlines(keepends=True)
    old_lines = old.splitlines(keepends=True)
    
    def normalize(s: str) -> str:
        return s.strip()
        
    old_norm = [normalize(l) for l in old_lines if normalize(l)]
    if not old_norm:
        return text
        
    text_norm = [normalize(l) for l in text_lines]
    
    for i in range(len(text_norm) - len(old_norm) + 1):
        match = True
        k = 0
        j = i
        while k < len(old_norm) and j < len(text_norm):
            if not text_norm[j]:
                j += 1
                continue
            if text_norm[j] != old_norm[k]:
                match = False
                break
            j += 1
            k += 1
            
        if match and k == len(old_norm):
            res = "".join(text_lines[:i]) + new
            if not new.endswith('\\n') and text_lines[j-1].endswith('\\n'):
                res += '\\n'
            res += "".join(text_lines[j:])
            return res
            
    return text

text = '''def hello():
    print("hi")
    
    # some comment
    return True
'''

old = '''def hello():
print("hi")
return True
'''

new = '''def hello():
    print("hello world")
    return False
'''

res = robust_replace(text, old, new)
print("=== RESULT ===")
print(res)

