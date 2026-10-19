"""Explicit, case-insensitive file ignore rules; no extension allowlist here."""
from fnmatch import fnmatchcase

def ignored(path,rules):
 value=str(path).replace('\\','/').casefold()
 name=value.rsplit('/',1)[-1]
 return any(fnmatchcase(value if '/' in rule.replace('\\','/') else name,rule.replace('\\','/').casefold()) for rule in rules if rule)

def clean_rules(values):
 if not isinstance(values,list) or len(values)>200:raise ValueError('Use at most 200 ignore rules')
 if any(not isinstance(v,str) or len(v)>1024 or '\n' in v or '\0' in v for v in values):raise ValueError('Invalid ignore rule')
 return list(dict.fromkeys(v.strip() for v in values if v.strip()))
