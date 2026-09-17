import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/tools.py')
text = path.read_text('utf-8')

robust_code = '''
def _fuzzy_replace(text: str, old: str, new: str, count: int) -> tuple[str, int]:
    if old in text:
        limit = -1 if int(count or 0) == 0 else int(count)
        changed = text.count(old) if limit < 0 else min(text.count(old), limit)
        return text.replace(old, new, limit), changed
        
    import re
    tokens = old.split()
    if not tokens:
        return text, 0
        
    escaped_tokens = [re.escape(t) for t in tokens]
    pattern_str = r'\\s+'.join(escaped_tokens)
    
    try:
        pattern = re.compile(pattern_str)
    except Exception:
        return text, 0
        
    matches = list(pattern.finditer(text))
    if len(matches) == 0:
        return text, 0
        
    limit = len(matches) if int(count or 0) == 0 else int(count)
    changed = min(len(matches), limit)
    
    res = text
    # Replace from back to front to preserve indices
    for match in reversed(matches[:changed]):
        start, end = match.start(), match.end()
        res = res[:start] + new + res[end:]
        
    return res, changed
'''

# We need to inject _fuzzy_replace into tools.py
# and update tool_replace_in_file

old_replace = '''
        if regex:
            updated, changed = re.subn(old, new, text, count=max(0, int(count or 0)))
        else:
            # count == 0 (the default) means "replace all matches". str.replace
            # treats 0 as "replace nothing", so 0 must map to -1 for a real
            # replace-all. A positive count caps the number of replacements.
            limit = -1 if int(count or 0) == 0 else int(count)
            changed = text.count(old) if limit < 0 else min(text.count(old), limit)
            updated = text.replace(old, new, limit)
'''

new_replace = '''
        if regex:
            updated, changed = re.subn(old, new, text, count=max(0, int(count or 0)))
        else:
            updated, changed = _fuzzy_replace(text, old, new, int(count or 0))
'''

if "def _fuzzy_replace" not in text:
    # insert before tool_replace_in_file
    text = text.replace('def tool_replace_in_file(', robust_code + '\ndef tool_replace_in_file(')
    text = text.replace(old_replace, new_replace)
    path.write_text(text, 'utf-8')
    print("Patched tool_replace_in_file with fuzzy replacement.")
else:
    print("Already patched.")

