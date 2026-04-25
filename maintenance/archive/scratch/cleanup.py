with open('/home/vu/toolsauto/scratch/graphql_inspector_e2e.py', 'r') as f:
    lines = f.readlines()
with open('/home/vu/toolsauto/scratch/graphql_inspector_e2e.py', 'w') as f:
    f.writelines(lines[:476] + lines[869:])
