"""Null encoding deep analysis."""
import tiktoken
enc = tiktoken.get_encoding('o200k_base')
def tc(t): return len(enc.encode(t, disallowed_special=()))

# TOON row 0
toon_r0 = 'usr_00000,Person 0,null,West Bengal,Acme Labs,null,0,[],False,null,null,null,null'
# Twig row 0 
twig_r0 = 'usr_00000|Person 0|#|West Bengal|&0|#|0|F|#|*'

print(f'TOON row 0: {tc(toon_r0)} tokens')
print(f'Twig row 0: {tc(twig_r0)} tokens')

# What if we use empty for null?
twig_r0_empty_null = 'usr_00000|Person 0||West Bengal|&0||0|F||*'
print(f'Twig row 0 (empty null): {tc(twig_r0_empty_null)} tokens')

# Test BPE merging
print()
print('=== BPE MERGING BEHAVIOR ===')
print(f'  ,null : {tc(",null")} tokens')
print(f'  ,null,null : {tc(",null,null")} tokens')
print(f'  ,null,null,null : {tc(",null,null,null")} tokens')
print(f'  |#|# : {tc("|#|#")} tokens')
print(f'  |#|#|# : {tc("|#|#|#")} tokens')
print(f'  || : {tc("||")} tokens')
print(f'  ||| : {tc("|||")} tokens')
print(f'  |||| : {tc("||||")} tokens')
print(f'  ,,, : {tc(",,")} tokens')

print()
print('=== NULL RUNS ===')
for n in range(1, 8):
    toon_nulls = ','.join(['null'] * n)
    twig_nulls = '|'.join(['#'] * n)
    twig_empty = '|'.join([''] * n)
    twig_rle = f'#{n}' if n >= 2 else '#'
    print(f'  {n} nulls: TOON={tc(toon_nulls)}, Twig(#)={tc(twig_nulls)}, Twig(empty)={tc(twig_empty)}, Twig(RLE)={tc(twig_rle)}')

# Key insight: what's the breakdown of TOON header vs Twig header tokens?
print()
toon_header = 'id,name,profile.city,profile.state,employment.company,employment.role,employment.years,skills,active,score,email,profile.pin,notes'
twig_header = """@shape:list
table:root
@tree
l1=profile^-
l2=employment^-
@dict
&0=Acme Labs
&1='713201
&2=*python^#^sql
@types
id
name
l1.city
l1.state
l2.company
l2.role
l2.years
active
score
skills
l1.pin
notes
email
@rows"""

print(f'TOON header: {tc(toon_header)} tokens')
print(f'Twig header: {tc(twig_header)} tokens')
print(f'Header diff: {tc(twig_header) - tc(toon_header)} tokens')

# What if we make Twig header as compact as possible?
twig_compact = """~L
T:l1=profile^-,l2=employment^-
D:&0=Acme Labs,&1='713201,&2=*python^#^sql
F:id,name,l1.city,l1.state,l2.company,l2.role,l2.years,active,score,skills,l1.pin,notes,email
R:"""
print(f'Twig compact header: {tc(twig_compact)} tokens')
print(f'Compact savings: {tc(twig_header) - tc(twig_compact)} tokens')

# Even more compact: use dotted paths instead of tree codes
twig_no_tree = """~L
D:&0=Acme Labs,&1='713201,&2=*python^#^sql
F:id,name,profile.city,profile.state,employment.company,employment.role,employment.years,active,score,skills,profile.pin,notes,email
R:"""
print(f'Twig no-tree header: {tc(twig_no_tree)} tokens')
print(f'No-tree savings: {tc(twig_header) - tc(twig_no_tree)} tokens')

# Test tab as delimiter instead of pipe
print()
print('=== TAB VS PIPE PER ROW ===')
twig_pipe = 'usr_00000|Person 0|#|West Bengal|&0|#|0|F|#|*'
twig_tab = 'usr_00000\tPerson 0\t#\tWest Bengal\t&0\t#\t0\tF\t#\t*'
twig_comma = 'usr_00000,Person 0,#,West Bengal,&0,#,0,F,#,*'
print(f'  Pipe:  {tc(twig_pipe)} tokens')
print(f'  Tab:   {tc(twig_tab)} tokens')
print(f'  Comma: {tc(twig_comma)} tokens')

# Test with 10 rows
from twig.codec import encode as twig_encode
from benchmarks.scaling_projection import make_sparse_record
recs = [make_sparse_record(i) for i in range(10)]
twig_out = twig_encode(recs)

# Convert pipe to tab
twig_tab_out = twig_out.replace('|', '\t')
print(f'\n  Full 10-row sparse:')
print(f'    Pipe version: {tc(twig_out)} tokens')
print(f'    Tab version:  {tc(twig_tab_out)} tokens')
print(f'    Tab savings:  {tc(twig_out) - tc(twig_tab_out)} tokens')

# What about using comma as delimiter?
twig_comma_out = twig_out.replace('|', ',')
print(f'    Comma version:  {tc(twig_comma_out)} tokens')
print(f'    Comma savings:  {tc(twig_out) - tc(twig_comma_out)} tokens')
