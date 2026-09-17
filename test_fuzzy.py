import re

def fuzzy_replace(text: str, old: str, new: str) -> str:
    if old in text:
        return text.replace(old, new)
        
    tokens = old.split()
    if not tokens:
        return text
        
    escaped_tokens = [re.escape(t) for t in tokens]
    pattern_str = r'\s+'.join(escaped_tokens)
    
    try:
        pattern = re.compile(pattern_str)
    except Exception:
        return text
        
    matches = list(pattern.finditer(text))
    
    if len(matches) == 1:
        match = matches[0]
        start, end = match.start(), match.end()
        res = text[:start] + new + text[end:]
        return res
        
    return text

text = '''def hello():
    print("hi")
    return True
'''

old = '''def hello():
print("hi")
return True'''

new = '''def hello():
    print("hello world")
    return False'''

res = fuzzy_replace(text, old, new)
print("=== RESULT ===")
print(res)

